"""Tests for pipeline.triage.methods_analysis — Stage 4 Sonnet risk assessment."""

from __future__ import annotations

from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import insert_paper


def _make_risk_result(aggregate: int = 10, tier: str = "high"):
    from pipeline.triage.llm import LLMResult

    return LLMResult(
        tool_input={
            "dimensions": {
                "pathogen_enhancement": {"score": 2, "justification": "GoF work"},
                "synthesis_barrier_lowering": {"score": 1, "justification": "Standard"},
                "select_agent_relevance": {"score": 2, "justification": "H5N1"},
                "novel_technique": {"score": 2, "justification": "New approach"},
                "information_hazard": {"score": 2, "justification": "Detailed"},
                "defensive_framing": {"score": 1, "justification": "Some discussion"},
            },
            "aggregate_score": aggregate,
            "risk_tier": tier,
            "summary": "This paper describes GoF research on H5N1.",
            "key_methods_of_concern": ["serial passage", "reverse genetics"],
            "recommended_action": "review",
        },
        raw_response='{"test": true}',
        input_tokens=500,
        output_tokens=200,
        cost_estimate_usd=0.005,
    )


class TestMethodsAnalysisSync:
    """Tests for run_methods_analysis in sync mode."""

    async def test_paper_assessed_and_updated(self, db_session: AsyncSession):
        from pipeline.models import AssessmentLog, PipelineStage, RecommendedAction, RiskTier
        from pipeline.triage.methods_analysis import run_methods_analysis

        paper = await insert_paper(
            db_session,
            title="H5N1 GoF",
            abstract="We enhanced transmissibility.",
            methods_section="Serial passage in ferrets.",
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=_make_risk_result(10, "high"))

        await run_methods_analysis(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-sonnet-4-6",
        )

        assert paper.pipeline_stage == PipelineStage.METHODS_ANALYSED
        assert paper.risk_tier == RiskTier.HIGH
        assert paper.aggregate_score == 10
        assert paper.recommended_action == RecommendedAction.REVIEW
        assert paper.stage2_result is not None

        logs = (await db_session.execute(select(AssessmentLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].stage == "methods_analysis"

    async def test_abstract_only_when_no_methods(self, db_session: AsyncSession):
        from pipeline.triage.methods_analysis import run_methods_analysis

        paper = await insert_paper(
            db_session,
            title="No fulltext paper",
            abstract="Abstract only.",
            methods_section=None,
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=_make_risk_result(3, "low"))

        await run_methods_analysis(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-sonnet-4-6",
        )

        # Verify the "NOTE:" abstract-only message was sent
        call_kwargs = mock_llm.call_tool.call_args.kwargs
        assert "NOTE:" in call_kwargs["user_message"]
        assert paper.risk_tier is not None

    async def test_risk_tier_thresholds(self, db_session: AsyncSession):
        """Verify risk tier enum mapping."""
        from pipeline.models import RiskTier
        from pipeline.triage.methods_analysis import run_methods_analysis

        paper = await insert_paper(db_session, title="Critical paper")
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=_make_risk_result(15, "critical"))

        await run_methods_analysis(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-sonnet-4-6",
        )

        assert paper.risk_tier == RiskTier.CRITICAL
        assert paper.aggregate_score == 15

    async def test_llm_error_skips_paper(self, db_session: AsyncSession):
        from pipeline.models import PipelineStage
        from pipeline.triage.llm import LLMResult
        from pipeline.triage.methods_analysis import run_methods_analysis

        paper = await insert_paper(db_session, title="Error paper")
        error_result = LLMResult(
            tool_input={},
            raw_response="",
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=0.0,
            error="Model refused",
        )
        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=error_result)

        await run_methods_analysis(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            use_batch=False,
            model="claude-sonnet-4-6",
        )

        assert paper.pipeline_stage == PipelineStage.INGESTED
        assert paper.risk_tier is None


class TestMethodsAnalysisBatch:
    """Tests for run_methods_analysis in batch mode."""

    async def test_batch_mode_processes_papers(self, db_session: AsyncSession):
        from pipeline.models import PipelineStage
        from pipeline.triage.methods_analysis import run_methods_analysis

        p1 = await insert_paper(db_session, title="Paper A")
        p2 = await insert_paper(db_session, title="Paper B")

        results = {
            str(p1.id): _make_risk_result(12, "high"),
            str(p2.id): _make_risk_result(2, "low"),
        }

        mock_llm = AsyncMock()
        mock_llm.submit_batch = AsyncMock(return_value="batch_999")
        mock_llm.collect_batch = AsyncMock(return_value=results)

        await run_methods_analysis(
            session=db_session,
            llm_client=mock_llm,
            papers=[p1, p2],
            use_batch=True,
            model="claude-sonnet-4-6",
        )

        assert p1.pipeline_stage == PipelineStage.METHODS_ANALYSED
        assert p2.pipeline_stage == PipelineStage.METHODS_ANALYSED
        assert p1.aggregate_score == 12
        assert p2.aggregate_score == 2
