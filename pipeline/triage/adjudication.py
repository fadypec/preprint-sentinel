"""Stage 5: Adjudication -- Opus contextual review.

Processes papers that passed methods analysis and meet the configured
risk tier threshold. Provides contextual assessment using enrichment
data from OpenAlex, Semantic Scholar, and ORCID.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.models import (
    AssessmentLog,
    Paper,
    PipelineStage,
    RecommendedAction,
    RiskTier,
)
from pipeline.triage.llm import LLMClient, LLMResult
from pipeline.triage.prompts import (
    ADJUDICATE_PAPER_TOOL,
    ADJUDICATION_SYSTEM_PROMPT,
    ADJUDICATION_VERSION,
    format_adjudication_message,
)

log = structlog.get_logger()

# Maps string values from LLM output to model enums
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

# Tier ordering for threshold comparison
_TIER_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}


def _tier_meets_threshold(tier: RiskTier | None, min_tier: str) -> bool:
    """Check if a paper's risk tier meets or exceeds the configured minimum.

    Papers with no risk tier (e.g. methods analysis failed/refused) always
    meet the threshold so they get Opus review rather than being silently
    auto-advanced with no assessment.
    """
    if tier is None:
        return True
    tier_val = _TIER_ORDER.get(tier.value, 0)
    min_val = _TIER_ORDER.get(min_tier, 0)
    return tier_val >= min_val


def _create_assessment_log(
    session: AsyncSession,
    paper: Paper,
    llm_result: LLMResult,
    model: str,
    user_message: str,
) -> None:
    """Create an AssessmentLog entry from an LLM result."""
    session.add(
        AssessmentLog(
            paper_id=paper.id,
            stage="adjudication",
            model_used=model,
            prompt_version=ADJUDICATION_VERSION,
            prompt_text=user_message,
            raw_response=llm_result.raw_response,
            parsed_result=llm_result.tool_input if not llm_result.error else None,
            input_tokens=llm_result.input_tokens,
            output_tokens=llm_result.output_tokens,
            cost_estimate_usd=llm_result.cost_estimate_usd,
            error=llm_result.error,
        )
    )


_REQUIRED_KEYS = {"adjusted_risk_tier", "adjusted_action", "confidence", "summary"}


def _validate_result(result: dict) -> str | None:
    """Return an error string if required keys are missing, else None."""
    missing = _REQUIRED_KEYS - result.keys()
    if missing:
        return f"Missing required keys: {sorted(missing)}"
    if result["adjusted_risk_tier"] not in _RISK_TIER_MAP:
        return f"Invalid adjusted_risk_tier: {result['adjusted_risk_tier']!r}"
    if result["adjusted_action"] not in _ACTION_MAP:
        return f"Invalid adjusted_action: {result['adjusted_action']!r}"
    return None


def _apply_result(paper: Paper, tool_input: dict) -> None:
    """Apply the adjudication result to the paper record."""
    paper.stage3_result = tool_input
    paper.risk_tier = _RISK_TIER_MAP.get(tool_input.get("adjusted_risk_tier", ""))
    paper.recommended_action = _ACTION_MAP.get(tool_input.get("adjusted_action", ""))
    paper.pipeline_stage = PipelineStage.ADJUDICATED


async def run_adjudication(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    model: str,
    min_tier: str,
) -> None:
    """Run Stage 5 adjudication on a list of papers.

    Papers below min_tier are auto-advanced to ADJUDICATED without Opus review.
    Papers at or above min_tier get full Opus contextual assessment.
    """
    if not papers:
        return

    total = len(papers)
    adjudicated_count = 0
    auto_advanced_count = 0

    for i, paper in enumerate(papers, 1):
        if not _tier_meets_threshold(paper.risk_tier, min_tier):
            # Auto-advance below-threshold papers
            paper.pipeline_stage = PipelineStage.ADJUDICATED
            auto_advanced_count += 1
            await session.flush()
            continue

        # Extract enrichment metadata
        enrichment_data = paper.enrichment_data or {}
        meta = enrichment_data.get("_meta", {})
        sources_failed = meta.get("sources_failed", [])

        user_msg = format_adjudication_message(
            title=paper.title,
            abstract=paper.abstract or "",
            methods=paper.methods_section,
            stage2_result=paper.stage2_result or {},
            enrichment_data=enrichment_data,
            sources_failed=sources_failed,
        )

        llm_result = await llm_client.call_tool(
            model=model,
            system_prompt=ADJUDICATION_SYSTEM_PROMPT,
            user_message=user_msg,
            tool=ADJUDICATE_PAPER_TOOL,
        )

        _create_assessment_log(session, paper, llm_result, model, user_msg)

        if llm_result.error:
            log.warning(
                "adjudication_error",
                paper_id=str(paper.id),
                error=llm_result.error,
            )
            # Advance paper so it doesn't retry forever; keep existing risk_tier from Stage 4
            paper.stage3_result = {"_error": llm_result.error}
            paper.pipeline_stage = PipelineStage.ADJUDICATED
            paper.needs_manual_review = True
        else:
            validation_err = _validate_result(llm_result.tool_input)
            if validation_err:
                log.warning(
                    "adjudication_invalid_response",
                    paper_id=str(paper.id),
                    error=validation_err,
                )
                paper.stage3_result = {"_error": validation_err, **llm_result.tool_input}
                paper.pipeline_stage = PipelineStage.ADJUDICATED
                paper.needs_manual_review = True
            else:
                _apply_result(paper, llm_result.tool_input)
                adjudicated_count += 1
                log.info(
                    "adjudication_result",
                    paper_id=str(paper.id),
                    adjusted_tier=llm_result.tool_input.get("adjusted_risk_tier"),
                    confidence=llm_result.tool_input.get("confidence"),
                    progress=f"{i}/{total}",
                )
        await session.flush()

    log.info(
        "adjudication_run_complete",
        total=total,
        adjudicated=adjudicated_count,
        auto_advanced=auto_advanced_count,
    )
