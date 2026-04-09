"""Stage 2: Coarse filter — Haiku binary screening.

Processes INGESTED papers and classifies them as relevant or not relevant
to dual-use research of concern. Papers where the model is confident they
are NOT relevant get filtered out. Everything else passes to Stage 3.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.models import AssessmentLog, Paper, PipelineStage
from pipeline.triage.llm import LLMClient, LLMResult
from pipeline.triage.prompts import (
    CLASSIFY_PAPER_TOOL,
    COARSE_FILTER_SYSTEM_PROMPT,
    COARSE_FILTER_VERSION,
    format_coarse_filter_message,
)

log = structlog.get_logger()


_REQUIRED_KEYS = {"relevant", "confidence", "reason"}


def _validate_result(result: dict) -> str | None:
    """Return an error string if required keys are missing, else None."""
    missing = _REQUIRED_KEYS - result.keys()
    if missing:
        return f"Missing required keys: {sorted(missing)}"
    if not isinstance(result["relevant"], bool):
        return f"'relevant' must be bool, got {type(result['relevant']).__name__}"
    return None


def _paper_passes(result: dict, threshold: float) -> bool:
    """Determine if a paper should advance past the coarse filter.

    Passes if relevant=True OR if model confidence is at or below threshold.
    Only filters papers the model is confident are NOT relevant.
    """
    if result.get("relevant", True):
        return True
    return result.get("confidence", 0.0) <= threshold


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
            stage="coarse_filter",
            model_used=model,
            prompt_version=COARSE_FILTER_VERSION,
            prompt_text=user_message,
            raw_response=llm_result.raw_response,
            parsed_result=llm_result.tool_input if not llm_result.error else None,
            input_tokens=llm_result.input_tokens,
            output_tokens=llm_result.output_tokens,
            cost_estimate_usd=llm_result.cost_estimate_usd,
            error=llm_result.error,
        )
    )


async def run_coarse_filter(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    use_batch: bool,
    model: str,
    threshold: float,
) -> list[Paper]:
    """Run Stage 2 coarse filter on a list of papers.

    Returns the subset of papers that pass the filter (advance to Stage 3).
    """
    if not papers:
        return []

    if use_batch:
        return await _run_batch(session, llm_client, papers, model, threshold)
    return await _run_sync(session, llm_client, papers, model, threshold)


async def _run_sync(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    model: str,
    threshold: float,
    concurrency: int = 30,
) -> list[Paper]:
    """Process papers concurrently with a semaphore."""
    passed: list[Paper] = []
    processed = 0
    total = len(papers)
    sem = asyncio.Semaphore(concurrency)

    async def _classify(paper: Paper) -> None:
        nonlocal processed
        try:
            async with sem:
                user_msg = format_coarse_filter_message(paper.title, paper.abstract or "")
                llm_result = await llm_client.call_tool(
                    model=model,
                    system_prompt=COARSE_FILTER_SYSTEM_PROMPT,
                    user_message=user_msg,
                    tool=CLASSIFY_PAPER_TOOL,
                )
        except Exception as exc:
            log.warning(
                "coarse_filter_exception",
                paper_id=str(paper.id),
                error=f"{type(exc).__name__}: {exc}",
            )
            processed += 1
            return

        _create_assessment_log(session, paper, llm_result, model, user_msg)

        if llm_result.error:
            log.warning("coarse_filter_error", paper_id=str(paper.id), error=llm_result.error)
        else:
            validation_err = _validate_result(llm_result.tool_input)
            if validation_err:
                log.warning(
                    "coarse_filter_invalid_response",
                    paper_id=str(paper.id),
                    error=validation_err,
                )
                # Fail-open: treat malformed response as passing so paper isn't silently dropped
                paper.stage1_result = llm_result.tool_input
                paper.pipeline_stage = PipelineStage.COARSE_FILTERED
                paper.coarse_filter_passed = True
                passed.append(paper)
            else:
                paper.stage1_result = llm_result.tool_input
                paper.pipeline_stage = PipelineStage.COARSE_FILTERED
                passes = _paper_passes(llm_result.tool_input, threshold)
                paper.coarse_filter_passed = passes

                if passes:
                    passed.append(paper)
                    log.info(
                        "coarse_filter_pass",
                        paper_id=str(paper.id),
                        relevant=llm_result.tool_input.get("relevant"),
                        confidence=llm_result.tool_input.get("confidence"),
                    )

        processed += 1
        if processed % 50 == 0 or processed == total:
            log.info("coarse_filter_progress", processed=processed, total=total)

    await asyncio.gather(*[_classify(p) for p in papers])
    await session.flush()

    log.info("coarse_filter_complete", total=total, passed=len(passed))
    return passed


async def _run_batch(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    model: str,
    threshold: float,
) -> list[Paper]:
    """Process papers via the batch API."""
    messages = []
    paper_map: dict[str, tuple[Paper, str]] = {}

    for paper in papers:
        user_msg = format_coarse_filter_message(paper.title, paper.abstract or "")
        custom_id = str(paper.id)
        messages.append((custom_id, user_msg))
        paper_map[custom_id] = (paper, user_msg)

    batch_id = await llm_client.submit_batch(
        model=model,
        system_prompt=COARSE_FILTER_SYSTEM_PROMPT,
        messages=messages,
        tool=CLASSIFY_PAPER_TOOL,
    )

    results = await llm_client.collect_batch(batch_id, model=model)

    passed: list[Paper] = []
    for custom_id, (paper, user_msg) in paper_map.items():
        llm_result = results.get(custom_id)
        if llm_result is None:
            log.warning("coarse_filter_missing_result", paper_id=custom_id)
            continue

        _create_assessment_log(session, paper, llm_result, model, user_msg)

        if llm_result.error:
            log.warning("coarse_filter_error", paper_id=custom_id, error=llm_result.error)
            continue

        paper.stage1_result = llm_result.tool_input
        paper.pipeline_stage = PipelineStage.COARSE_FILTERED
        passes = _paper_passes(llm_result.tool_input, threshold)
        paper.coarse_filter_passed = passes

        if passes:
            passed.append(paper)

    await session.flush()
    log.info("coarse_filter_batch_complete", total=len(papers), passed=len(passed))
    return passed
