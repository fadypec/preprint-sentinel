#!/usr/bin/env python3
"""Fix systematic JSON parsing bug in methods analysis results.

The bug: LLM responses are being stored with the entire JSON response
as a string in the "dimensions" field instead of properly parsed.

This script:
1. Finds papers with malformed stage2_result where dimensions is a string
2. Parses the JSON from the dimensions field
3. Reconstructs the proper stage2_result structure
4. Updates database records with corrected data
"""

import asyncio
import json
from typing import Any

import structlog
from sqlalchemy import select, text

from pipeline.config import get_settings
from pipeline.db import make_engine, make_session_factory
from pipeline.models import Paper, RecommendedAction, RiskTier

log = structlog.get_logger()

# Maps from the LLM output strings to model enums
_RISK_TIER_MAP = {
    "low": RiskTier.LOW,
    "medium": RiskTier.MEDIUM,
    "high": RiskTier.HIGH,
    "critical": RiskTier.CRITICAL,
}

_ACTION_MAP = {
    "archive": RecommendedAction.ARCHIVE,
    "monitor": RecommendedAction.MONITOR,
    "review": RecommendedAction.REVIEW,
    "escalate": RecommendedAction.ESCALATE,
}


def parse_malformed_result(stage2_result: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a malformed stage2_result and return the corrected structure.

    Args:
        stage2_result: The corrupted result with dimensions as a string

    Returns:
        Corrected stage2_result dictionary, or None if parsing fails
    """
    if not isinstance(stage2_result, dict):
        return None

    dimensions_str = stage2_result.get("dimensions")
    if not isinstance(dimensions_str, str):
        return None

    # Try multiple parsing strategies
    strategies = [
        _parse_strategy_complete_json,
        _parse_strategy_dimension_boundary,
        _parse_strategy_truncated_json,
        _parse_strategy_control_chars,
        _parse_strategy_regex_extraction,
    ]

    for strategy in strategies:
        try:
            result = strategy(dimensions_str, stage2_result)
            if result is not None:
                return result
        except Exception as e:
            log.debug("parsing_strategy_failed", strategy=strategy.__name__, error=str(e))

    log.warning("all_parsing_strategies_failed", content_length=len(dimensions_str))
    return None


def _parse_strategy_complete_json(
    dimensions_str: str, stage2_result: dict
) -> dict[str, Any] | None:
    """Try to parse as complete JSON first."""
    try:
        full_response = json.loads(dimensions_str)
        if "dimensions" in full_response:
            return validate_and_build_result(stage2_result, full_response)
    except json.JSONDecodeError:
        pass
    return None


def _parse_strategy_dimension_boundary(
    dimensions_str: str, stage2_result: dict
) -> dict[str, Any] | None:
    """Handle malformed structure by finding dimension boundary."""
    lines = dimensions_str.strip().split("\n")

    # Find the line where the dimensions object ends (look for "},)
    dimension_end = -1
    for i, line in enumerate(lines):
        if line.strip() == "},":
            # Check if the next line starts a top-level field
            if i + 1 < len(lines) and lines[i + 1].strip().startswith('"aggregate_score"'):
                dimension_end = i
                break

    if dimension_end == -1:
        return None

    # Split into dimensions part and top-level fields part
    dimensions_lines = lines[:dimension_end] + ["}"]  # Replace }, with }
    top_level_lines = lines[dimension_end + 1 :]

    # Parse dimensions object
    dimensions_json = "\n".join(dimensions_lines)
    dimensions_obj = json.loads(dimensions_json)

    # Parse top-level fields - add opening brace
    top_level_json = "{\n" + "\n".join(top_level_lines)
    # Remove trailing comma if exists and add closing brace if missing
    top_level_json = top_level_json.rstrip().rstrip(",") + "\n}"
    top_level_obj = json.loads(top_level_json)

    # Combine into proper structure
    full_response = {"dimensions": dimensions_obj, **top_level_obj}

    return validate_and_build_result(stage2_result, full_response)


def _parse_strategy_truncated_json(
    dimensions_str: str, stage2_result: dict
) -> dict[str, Any] | None:
    """Handle truncated JSON by finding the last complete field."""
    # Look for truncated JSON that ends abruptly
    # Try to find the last complete field and extract what we can

    # Common truncation patterns
    truncation_patterns = [
        r'(.*)"recommended_action":\s*"([^"]*)"[^}]*$',
        r'(.*)"aggregate_score":\s*(\d+)[^}]*$',
        r'(.*)"risk_tier":\s*"([^"]*)"[^}]*$',
    ]

    for pattern in truncation_patterns:
        import re

        match = re.search(pattern, dimensions_str, re.DOTALL)
        if match:
            # Try to reconstruct based on what we found
            try:
                # This is a simplified reconstruction - would need more logic for full implementation
                return _reconstruct_from_partial_match(match, stage2_result)
            except:
                continue

    return None


def _parse_strategy_control_chars(
    dimensions_str: str, stage2_result: dict
) -> dict[str, Any] | None:
    """Handle JSON with control characters by cleaning them."""
    import re

    # Remove control characters except newlines and tabs
    cleaned = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]", "", dimensions_str)

    if cleaned != dimensions_str:
        # Try parsing the cleaned version with other strategies
        for strategy in [_parse_strategy_complete_json, _parse_strategy_dimension_boundary]:
            try:
                result = strategy(cleaned, stage2_result)
                if result is not None:
                    return result
            except:
                continue

    return None


def _parse_strategy_regex_extraction(
    dimensions_str: str, stage2_result: dict
) -> dict[str, Any] | None:
    """Extract fields using regex patterns as last resort."""
    import re

    # Extract individual fields using regex
    extracted = {}

    # Extract aggregate_score
    score_match = re.search(r'"aggregate_score":\s*(\d+)', dimensions_str)
    if score_match:
        extracted["aggregate_score"] = int(score_match.group(1))

    # Extract risk_tier
    tier_match = re.search(r'"risk_tier":\s*"([^"]*)"', dimensions_str)
    if tier_match:
        extracted["risk_tier"] = tier_match.group(1)

    # Extract summary
    summary_match = re.search(r'"summary":\s*"((?:[^"\\]|\\.)*)"', dimensions_str)
    if summary_match:
        extracted["summary"] = summary_match.group(1).replace('\\"', '"')

    # Extract recommended_action
    action_match = re.search(r'"recommended_action":\s*"([^"]*)"', dimensions_str)
    if action_match:
        extracted["recommended_action"] = action_match.group(1)

    # Try to extract dimensions (simplified)
    dimensions = {}
    dim_names = [
        "pathogen_enhancement",
        "synthesis_barrier_lowering",
        "select_agent_relevance",
        "novel_technique",
        "information_hazard",
        "defensive_framing",
    ]

    for dim_name in dim_names:
        score_pattern = f'"{dim_name}":\\s*{{[^}}]*"score":\\s*(\\d+)'
        score_match = re.search(score_pattern, dimensions_str)
        if score_match:
            dimensions[dim_name] = {
                "score": int(score_match.group(1)),
                "justification": "Recovered from corrupted data - justification unavailable",
            }

    # Only proceed if we extracted enough core data
    if len(extracted) >= 3 and dimensions:  # Need at least score, tier, action and some dimensions
        extracted["dimensions"] = dimensions
        extracted["key_methods_of_concern"] = []  # Default empty

        # Fill in missing fields with defaults
        if "summary" not in extracted:
            extracted["summary"] = "Summary recovered from corrupted data"

        return validate_and_build_result(stage2_result, extracted)

    return None


def _reconstruct_from_partial_match(match, stage2_result: dict) -> dict[str, Any] | None:
    """Helper to reconstruct data from regex match - simplified version."""
    # This is a placeholder - full implementation would be more complex
    return None


def validate_and_build_result(
    stage2_result: dict[str, Any], full_response: dict[str, Any]
) -> dict[str, Any] | None:
    """Validate parsed response and build corrected result."""
    # Validate that we have all required fields
    required_fields = {
        "dimensions",
        "aggregate_score",
        "risk_tier",
        "summary",
        "key_methods_of_concern",
        "recommended_action",
    }

    if not all(field in full_response for field in required_fields):
        missing = required_fields - set(full_response.keys())
        log.warning("parsed_response_missing_fields", missing=missing)
        return None

    # Validate enum values
    if full_response["risk_tier"] not in _RISK_TIER_MAP:
        log.warning("invalid_risk_tier", tier=full_response["risk_tier"])
        return None

    if full_response["recommended_action"] not in _ACTION_MAP:
        log.warning("invalid_action", action=full_response["recommended_action"])
        return None

    # Preserve any existing metadata from the corrupted result
    corrected = {
        "_error": stage2_result.get("_error"),  # Preserve error info if exists
        "_model": stage2_result.get("_model"),  # Preserve model info if exists
    }

    # Add the properly parsed data
    corrected.update(full_response)

    # Remove any None values
    return {k: v for k, v in corrected.items() if v is not None}


async def fix_parsing_bug(dry_run: bool = True) -> None:
    """Fix the systematic JSON parsing bug affecting methods analysis results."""
    settings = get_settings()
    engine = make_engine(settings.database_url.get_secret_value())
    session_factory = make_session_factory(engine)

    async with session_factory() as session:
        # Find papers with string dimensions (the corruption signature)
        stmt = text("""
            SELECT id, doi, stage2_result
            FROM papers
            WHERE stage2_result ? '_error'
            AND stage2_result->>'_error' LIKE 'Missing required keys%'
            AND jsonb_typeof(stage2_result->'dimensions') = 'string'
        """)
        result = await session.execute(stmt)
        corrupted_papers = list(result.all())

        log.info("found_corrupted_papers", count=len(corrupted_papers))

        if not corrupted_papers:
            log.info("no_corrupted_papers_found")
            return

        fixed = 0
        failed = 0

        for paper_id, doi, stage2_result in corrupted_papers:
            log.info("processing_paper", paper_id=str(paper_id), doi=doi)

            # Parse the malformed result
            corrected_result = parse_malformed_result(stage2_result)

            if corrected_result is None:
                log.warning("failed_to_fix", paper_id=str(paper_id), doi=doi)
                failed += 1
                continue

            if dry_run:
                log.info(
                    "would_fix_paper",
                    paper_id=str(paper_id),
                    doi=doi,
                    old_keys=list(stage2_result.keys()),
                    new_keys=list(corrected_result.keys()),
                    risk_tier=corrected_result.get("risk_tier"),
                    aggregate_score=corrected_result.get("aggregate_score"),
                )
                fixed += 1
            else:
                # Apply the fix to the database
                stmt = select(Paper).where(Paper.id == paper_id)
                paper_result = await session.execute(stmt)
                paper = paper_result.scalar_one()

                # Update paper with corrected data
                paper.stage2_result = corrected_result
                paper.aggregate_score = corrected_result.get("aggregate_score")
                paper.risk_tier = _RISK_TIER_MAP.get(corrected_result.get("risk_tier"))
                paper.recommended_action = _ACTION_MAP.get(
                    corrected_result.get("recommended_action")
                )

                log.info(
                    "fixed_paper",
                    paper_id=str(paper_id),
                    doi=doi,
                    risk_tier=paper.risk_tier,
                    aggregate_score=paper.aggregate_score,
                )
                fixed += 1

        if not dry_run:
            await session.commit()
            log.info("committed_changes")

        log.info(
            "fix_complete",
            total_corrupted=len(corrupted_papers),
            fixed=fixed,
            failed=failed,
            dry_run=dry_run,
        )

    await engine.dispose()


if __name__ == "__main__":
    import sys

    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("DRY RUN - No changes will be made. Use --apply to execute fixes.")
    else:
        print("APPLYING FIXES - Database will be modified.")

    asyncio.run(fix_parsing_bug(dry_run=dry_run))
