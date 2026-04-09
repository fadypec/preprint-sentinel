"""Tests for pipeline.triage.adjudication -- Stage 5 Opus contextual review."""

from __future__ import annotations

from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import insert_paper


def _make_adjudication_result(
    tier: str = "high",
    action: str = "review",
    confidence: float = 0.85,
    partial: bool = False,
    missing: list[str] | None = None,
):
    from pipeline.triage.llm import LLMResult

    return LLMResult(
        tool_input={
            "adjusted_risk_tier": tier,
            "adjusted_action": action,
            "confidence": confidence,
            "partial_enrichment": partial,
            "missing_sources": missing or [],
            "institutional_context": "Well-established virology lab at MIT.",
            "durc_oversight_indicators": ["IBC approval cited", "NIH DURC review"],
            "adjustment_reasoning": "Confirmed high risk due to GoF methodology.",
            "summary": "This paper describes GoF research by a well-known lab. Risk confirmed.",
        },
        raw_response='{"test": true}',
        input_tokens=1000,
        output_tokens=500,
        cost_estimate_usd=0.05,
    )


class TestAdjudication:
    """Tests for run_adjudication."""

    async def test_paper_assessed_and_updated(self, db_session: AsyncSession):
        from pipeline.models import (
            AssessmentLog,
            PipelineStage,
            RecommendedAction,
            RiskTier,
        )
        from pipeline.triage.adjudication import run_adjudication

        paper = await insert_paper(
            db_session,
            title="H5N1 GoF",
            abstract="We enhanced transmissibility.",
            methods_section="Serial passage in ferrets.",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.HIGH,
            recommended_action=RecommendedAction.REVIEW,
            stage2_result={"risk_tier": "high", "aggregate_score": 10},
            enrichment_data={
                "openalex": {"primary_institution": "MIT"},
                "_meta": {
                    "sources_succeeded": ["openalex", "semantic_scholar", "orcid"],
                    "sources_failed": [],
                },
            },
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=_make_adjudication_result())

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        assert paper.pipeline_stage == PipelineStage.ADJUDICATED
        assert paper.risk_tier == RiskTier.HIGH
        assert paper.recommended_action == RecommendedAction.REVIEW
        assert paper.stage3_result is not None
        assert paper.stage3_result["adjusted_risk_tier"] == "high"
        assert paper.stage3_result["institutional_context"] == (
            "Well-established virology lab at MIT."
        )

        logs = (await db_session.execute(select(AssessmentLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].stage == "adjudication"
        assert logs[0].model_used == "claude-opus-4-6"

    async def test_partial_enrichment_flag_propagated(self, db_session: AsyncSession):
        from pipeline.models import PipelineStage, RecommendedAction, RiskTier
        from pipeline.triage.adjudication import run_adjudication

        paper = await insert_paper(
            db_session,
            title="Partial enrichment paper",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.HIGH,
            recommended_action=RecommendedAction.REVIEW,
            stage2_result={"risk_tier": "high"},
            enrichment_data={
                "openalex": {"primary_institution": "MIT"},
                "_meta": {
                    "sources_succeeded": ["openalex"],
                    "sources_failed": ["semantic_scholar", "orcid"],
                },
            },
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(
            return_value=_make_adjudication_result(
                partial=True,
                missing=["semantic_scholar", "orcid"],
                confidence=0.6,
            )
        )

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        assert paper.pipeline_stage == PipelineStage.ADJUDICATED
        assert paper.stage3_result["partial_enrichment"] is True
        assert paper.stage3_result["confidence"] == 0.6

    async def test_llm_error_advances_paper_with_review_flag(self, db_session: AsyncSession):
        """Papers with adjudication errors advance to ADJUDICATED (not stuck)
        but get needs_manual_review=True and keep their Stage 4 risk_tier."""
        from pipeline.models import PipelineStage, RecommendedAction, RiskTier
        from pipeline.triage.adjudication import run_adjudication
        from pipeline.triage.llm import LLMResult

        paper = await insert_paper(
            db_session,
            title="Error paper",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.HIGH,
            recommended_action=RecommendedAction.REVIEW,
            stage2_result={"risk_tier": "high"},
            enrichment_data={"_meta": {"sources_succeeded": [], "sources_failed": []}},
        )

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

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        assert paper.pipeline_stage == PipelineStage.ADJUDICATED
        assert paper.risk_tier == RiskTier.HIGH  # Preserved from Stage 4
        assert paper.needs_manual_review is True
        assert paper.stage3_result["_error"] == "Model refused"

    async def test_below_threshold_paper_auto_advanced(self, db_session: AsyncSession):
        """Papers below the adjudication threshold are auto-advanced without Opus."""
        from pipeline.models import PipelineStage, RecommendedAction, RiskTier
        from pipeline.triage.adjudication import run_adjudication

        paper = await insert_paper(
            db_session,
            title="Low risk paper",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.MEDIUM,
            recommended_action=RecommendedAction.MONITOR,
            stage2_result={"risk_tier": "medium"},
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock()

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        # Paper auto-advanced to ADJUDICATED without LLM call
        assert paper.pipeline_stage == PipelineStage.ADJUDICATED
        assert paper.stage3_result is None
        # risk_tier and recommended_action remain from Stage 4
        assert paper.risk_tier == RiskTier.MEDIUM
        assert paper.recommended_action == RecommendedAction.MONITOR
        mock_llm.call_tool.assert_not_called()

    async def test_tier_threshold_filtering(self, db_session: AsyncSession):
        """Only papers at or above min_tier get Opus review."""
        from pipeline.models import PipelineStage, RecommendedAction, RiskTier
        from pipeline.triage.adjudication import run_adjudication

        high_paper = await insert_paper(
            db_session,
            title="High risk paper",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.HIGH,
            recommended_action=RecommendedAction.REVIEW,
            stage2_result={"risk_tier": "high"},
            enrichment_data={"_meta": {"sources_succeeded": [], "sources_failed": []}},
        )
        low_paper = await insert_paper(
            db_session,
            title="Low risk paper",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.LOW,
            recommended_action=RecommendedAction.ARCHIVE,
            stage2_result={"risk_tier": "low"},
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(return_value=_make_adjudication_result())

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[high_paper, low_paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        # High paper gets Opus review
        assert high_paper.pipeline_stage == PipelineStage.ADJUDICATED
        assert high_paper.stage3_result is not None

        # Low paper auto-advanced
        assert low_paper.pipeline_stage == PipelineStage.ADJUDICATED
        assert low_paper.stage3_result is None
        assert low_paper.risk_tier == RiskTier.LOW

        # Only one LLM call (for the high paper)
        assert mock_llm.call_tool.call_count == 1

    async def test_risk_tier_downgrade(self, db_session: AsyncSession):
        """Opus can downgrade a paper's risk tier."""
        from pipeline.models import PipelineStage, RecommendedAction, RiskTier
        from pipeline.triage.adjudication import run_adjudication

        paper = await insert_paper(
            db_session,
            title="Downgraded paper",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=RiskTier.HIGH,
            recommended_action=RecommendedAction.REVIEW,
            stage2_result={"risk_tier": "high"},
            enrichment_data={"_meta": {"sources_succeeded": [], "sources_failed": []}},
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(
            return_value=_make_adjudication_result(tier="medium", action="monitor")
        )

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        assert paper.risk_tier == RiskTier.MEDIUM
        assert paper.recommended_action == RecommendedAction.MONITOR

    async def test_null_risk_tier_gets_opus_review(self, db_session: AsyncSession):
        """Papers with NULL risk_tier (e.g. methods analysis failed) should get
        Opus review rather than being silently auto-advanced."""
        from pipeline.models import PipelineStage, RiskTier
        from pipeline.triage.adjudication import run_adjudication

        paper = await insert_paper(
            db_session,
            title="Refused paper about toxin",
            pipeline_stage=PipelineStage.METHODS_ANALYSED,
            risk_tier=None,
            stage2_result={"_error": "Model refused to process this content"},
            enrichment_data={"_meta": {"sources_succeeded": [], "sources_failed": []}},
        )

        mock_llm = AsyncMock()
        mock_llm.call_tool = AsyncMock(
            return_value=_make_adjudication_result(tier="high", action="review")
        )

        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[paper],
            model="claude-opus-4-6",
            min_tier="high",
        )

        # Paper should get Opus review (not auto-advanced)
        assert mock_llm.call_tool.call_count == 1
        assert paper.pipeline_stage == PipelineStage.ADJUDICATED
        assert paper.risk_tier == RiskTier.HIGH
        assert paper.stage3_result is not None

    async def test_empty_papers_list(self, db_session: AsyncSession):
        """Empty list does nothing."""
        from pipeline.triage.adjudication import run_adjudication

        mock_llm = AsyncMock()
        await run_adjudication(
            session=db_session,
            llm_client=mock_llm,
            papers=[],
            model="claude-opus-4-6",
            min_tier="high",
        )
        mock_llm.call_tool.assert_not_called()
