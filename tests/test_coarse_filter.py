"""Tests for pipeline.triage.coarse_filter — Stage 2 Haiku screening."""

from __future__ import annotations

from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import insert_paper


def _make_llm_result(relevant: bool, confidence: float, reason: str = "test"):
    from pipeline.triage.llm import LLMResult

    return LLMResult(
        tool_input={"relevant": relevant, "confidence": confidence, "reason": reason},
        raw_response='{"test": true}',
        input_tokens=100,
        output_tokens=50,
        cost_estimate_usd=0.001,
    )


class TestCoarseFilterSync:
    """Tests for run_coarse_filter in sync mode."""

    async def test_relevant_paper_passes(self, db_session: AsyncSession):
        from pipeline.models import AssessmentLog, PipelineStage
        from pipeline.triage.coarse_filter import run_coarse_filter

        paper = await insert_paper(db_session, title="GoF H5N1")
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(
            return_value=_make_llm_result(relevant=True, confidence=0.95)
        )

        passed = await run_coarse_filter(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-haiku-4-5-20251001",
            threshold=0.8,
        )

        assert len(passed) == 1
        assert passed[0].id == paper.id
        assert paper.pipeline_stage == PipelineStage.COARSE_FILTERED
        assert paper.stage1_result["relevant"] is True

        # AssessmentLog created
        logs = (await db_session.execute(select(AssessmentLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].stage == "coarse_filter"

    async def test_irrelevant_high_confidence_filtered(self, db_session: AsyncSession):
        from pipeline.models import PipelineStage
        from pipeline.triage.coarse_filter import run_coarse_filter

        paper = await insert_paper(db_session, title="Basic epidemiology")
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(
            return_value=_make_llm_result(relevant=False, confidence=0.95)
        )

        passed = await run_coarse_filter(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-haiku-4-5-20251001",
            threshold=0.8,
        )

        assert len(passed) == 0
        assert paper.pipeline_stage == PipelineStage.COARSE_FILTERED
        assert paper.stage1_result["relevant"] is False

    async def test_irrelevant_low_confidence_passes(self, db_session: AsyncSession):
        """Low confidence non-relevant still passes — err on inclusion."""
        from pipeline.triage.coarse_filter import run_coarse_filter

        paper = await insert_paper(db_session, title="Borderline paper")
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(
            return_value=_make_llm_result(relevant=False, confidence=0.6)
        )

        passed = await run_coarse_filter(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-haiku-4-5-20251001",
            threshold=0.8,
        )

        assert len(passed) == 1

    async def test_llm_error_skips_paper(self, db_session: AsyncSession):
        from pipeline.models import PipelineStage
        from pipeline.triage.coarse_filter import run_coarse_filter
        from pipeline.triage.llm import LLMResult

        paper = await insert_paper(db_session, title="Error paper")
        error_result = LLMResult(
            tool_input={},
            raw_response="",
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=0.0,
            error="No tool_use block in response",
        )
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=error_result)

        passed = await run_coarse_filter(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-haiku-4-5-20251001",
            threshold=0.8,
        )

        assert len(passed) == 0
        # Paper stays at INGESTED when there's an error
        assert paper.pipeline_stage == PipelineStage.INGESTED


class TestCoarseFilterBatch:
    """Tests for run_coarse_filter in batch mode."""

    async def test_batch_mode_processes_papers(self, db_session: AsyncSession):
        from pipeline.triage.coarse_filter import run_coarse_filter

        p1 = await insert_paper(db_session, title="Paper A")
        p2 = await insert_paper(db_session, title="Paper B")

        results = {
            str(p1.id): _make_llm_result(relevant=True, confidence=0.9),
            str(p2.id): _make_llm_result(relevant=False, confidence=0.95),
        }

        mock_llm = AsyncMock()
        mock_llm.submit_batch = AsyncMock(return_value="batch_123")
        mock_llm.collect_batch = AsyncMock(return_value=results)

        passed = await run_coarse_filter(
            session=db_session,
            llm_client=mock_llm,
            papers=[p1, p2],
            use_batch=True,
            model="claude-haiku-4-5-20251001",
            threshold=0.8,
        )

        assert len(passed) == 1
        assert passed[0].id == p1.id
