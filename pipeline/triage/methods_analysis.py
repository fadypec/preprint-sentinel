"""Stage 4: Methods analysis — Sonnet 6-dimension risk rubric assessment.

Processes papers that passed the coarse filter, assessing their methods
section (or abstract if full text was unavailable) against a detailed
dual-use risk rubric.
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
    ASSESS_DURC_RISK_TOOL,
    METHODS_ANALYSIS_SYSTEM_PROMPT,
    METHODS_ANALYSIS_VERSION,
    format_methods_analysis_message,
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
            stage="methods_analysis",
            model_used=model,
            prompt_version=METHODS_ANALYSIS_VERSION,
            prompt_text=user_message,
            raw_response=llm_result.raw_response,
            parsed_result=llm_result.tool_input if not llm_result.error else None,
            input_tokens=llm_result.input_tokens,
            output_tokens=llm_result.output_tokens,
            cost_estimate_usd=llm_result.cost_estimate_usd,
            error=llm_result.error,
        )
    )


_REQUIRED_KEYS = {"aggregate_score", "risk_tier", "recommended_action", "summary", "dimensions"}


def _validate_result(result: dict) -> str | None:
    """Return an error string if required keys are missing, else None."""
    missing = _REQUIRED_KEYS - result.keys()
    if missing:
        return f"Missing required keys: {sorted(missing)}"
    if result["risk_tier"] not in _RISK_TIER_MAP:
        return f"Invalid risk_tier: {result['risk_tier']!r}"
    if result["recommended_action"] not in _ACTION_MAP:
        return f"Invalid recommended_action: {result['recommended_action']!r}"
    return None


def _apply_result(paper: Paper, tool_input: dict) -> None:
    """Apply the LLM assessment result to the paper record."""
    # stage2_result = second LLM stage (methods analysis);
    # column naming is sequential (stage1/2/3), not by pipeline stage number.
    paper.stage2_result = tool_input
    paper.aggregate_score = tool_input.get("aggregate_score")
    paper.risk_tier = _RISK_TIER_MAP.get(tool_input.get("risk_tier", ""))
    paper.recommended_action = _ACTION_MAP.get(tool_input.get("recommended_action", ""))
    paper.pipeline_stage = PipelineStage.METHODS_ANALYSED


async def run_methods_analysis(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    use_batch: bool,
    model: str,
) -> None:
    """Run Stage 4 methods analysis on a list of papers."""
    if not papers:
        return

    if use_batch:
        await _run_batch(session, llm_client, papers, model)
    else:
        await _run_sync(session, llm_client, papers, model)


async def _run_sync(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    model: str,
) -> None:
    """Process papers one at a time."""
    total = len(papers)
    for i, paper in enumerate(papers, 1):
        user_msg = format_methods_analysis_message(
            paper.title, paper.abstract or "", methods=paper.methods_section
        )

        llm_result = await llm_client.call_tool(
            model=model,
            system_prompt=METHODS_ANALYSIS_SYSTEM_PROMPT,
            user_message=user_msg,
            tool=ASSESS_DURC_RISK_TOOL,
        )

        _create_assessment_log(session, paper, llm_result, model, user_msg)

        if llm_result.error:
            log.warning("methods_analysis_error", paper_id=str(paper.id), error=llm_result.error)
        else:
            validation_err = _validate_result(llm_result.tool_input)
            if validation_err:
                log.warning(
                    "methods_analysis_invalid_response",
                    paper_id=str(paper.id),
                    error=validation_err,
                )
            else:
                _apply_result(paper, llm_result.tool_input)
                log.info(
                    "methods_analysis_result",
                    paper_id=str(paper.id),
                    risk_tier=paper.risk_tier,
                    aggregate_score=paper.aggregate_score,
                    progress=f"{i}/{total}",
                )
        await session.flush()

        if i % 10 == 0 or i == total:
            log.info("methods_analysis_progress", processed=i, total=total)

    log.info("methods_analysis_sync_complete", total=total)


async def _run_batch(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    model: str,
) -> None:
    """Process papers via the batch API."""
    messages = []
    paper_map: dict[str, tuple[Paper, str]] = {}

    for paper in papers:
        user_msg = format_methods_analysis_message(
            paper.title, paper.abstract or "", methods=paper.methods_section
        )
        custom_id = str(paper.id)
        messages.append((custom_id, user_msg))
        paper_map[custom_id] = (paper, user_msg)

    batch_id = await llm_client.submit_batch(
        model=model,
        system_prompt=METHODS_ANALYSIS_SYSTEM_PROMPT,
        messages=messages,
        tool=ASSESS_DURC_RISK_TOOL,
    )

    results = await llm_client.collect_batch(batch_id, model=model)

    for custom_id, (paper, user_msg) in paper_map.items():
        llm_result = results.get(custom_id)
        if llm_result is None:
            log.warning("methods_analysis_missing_result", paper_id=custom_id)
            session.add(
                AssessmentLog(
                    paper_id=paper.id,
                    stage="methods_analysis",
                    model_used=model,
                    prompt_version=METHODS_ANALYSIS_VERSION,
                    prompt_text=user_msg,
                    raw_response="",
                    parsed_result=None,
                    input_tokens=0,
                    output_tokens=0,
                    cost_estimate_usd=0.0,
                    error="No result returned from batch",
                )
            )
            continue

        _create_assessment_log(session, paper, llm_result, model, user_msg)

        if llm_result.error:
            log.warning("methods_analysis_error", paper_id=custom_id, error=llm_result.error)
            continue

        validation_err = _validate_result(llm_result.tool_input)
        if validation_err:
            log.warning(
                "methods_analysis_invalid_response",
                paper_id=custom_id,
                error=validation_err,
            )
            continue

        _apply_result(paper, llm_result.tool_input)

    await session.flush()
    log.info("methods_analysis_batch_complete", total=len(papers))
