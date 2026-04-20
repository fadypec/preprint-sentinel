"""Tests for pipeline.orchestrator -- daily pipeline orchestrator."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _make_mock_settings() -> MagicMock:
    """Create a mock settings object with all required attributes."""
    mock_settings = MagicMock()
    mock_settings.database_url = MagicMock()
    mock_settings.database_url.get_secret_value = MagicMock(
        return_value="sqlite+aiosqlite:///:memory:"
    )
    mock_settings.anthropic_api_key = MagicMock()
    mock_settings.anthropic_api_key.get_secret_value = MagicMock(return_value="sk-test")
    mock_settings.stage1_model = "claude-haiku-4-5-20251001"
    mock_settings.stage2_model = "claude-sonnet-4-6"
    mock_settings.stage3_model = "claude-opus-4-6"
    mock_settings.coarse_filter_threshold = 0.8
    mock_settings.use_batch_api = False
    mock_settings.adjudication_min_tier = "high"
    mock_settings.biorxiv_request_delay = 0
    mock_settings.europepmc_request_delay = 0
    mock_settings.pubmed_request_delay = 0
    mock_settings.ncbi_api_key = ""
    mock_settings.pubmed_query_mode = "all"
    mock_settings.pubmed_mesh_query = ""
    mock_settings.stage2_fallback_models = "claude-opus-4-6"
    return mock_settings



class TestRunDailyPipeline:
    """Tests for run_daily_pipeline."""

    async def test_stages_run_in_order(self, db_engine, db_session: AsyncSession):
        from pipeline.orchestrator import run_daily_pipeline

        call_order = []

        async def mock_ingest(session, settings, from_date, to_date):
            call_order.append("ingest")
            return []

        async def mock_dedup(session, papers, settings=None):
            call_order.append("dedup")
            return papers, 0

        async def mock_coarse(session, llm_client, papers, use_batch, model, threshold):
            call_order.append("coarse_filter")
            return papers

        async def mock_fulltext(session, papers, settings):
            call_order.append("fulltext")

        async def mock_methods(session, llm_client, papers, use_batch, model, fallback_models=None):
            call_order.append("methods_analysis")

        async def mock_enrich(session, papers, settings):
            call_order.append("enrichment")
            return papers

        async def mock_adjudicate(session, llm_client, papers, model, min_tier):
            call_order.append("adjudication")

        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        mock_settings = MagicMock()
        mock_settings.database_url = MagicMock()
        mock_settings.database_url.get_secret_value = MagicMock(
            return_value="sqlite+aiosqlite:///:memory:"
        )
        mock_settings.anthropic_api_key = MagicMock()
        mock_settings.anthropic_api_key.get_secret_value = MagicMock(return_value="sk-test")
        mock_settings.stage1_model = "claude-haiku-4-5-20251001"
        mock_settings.stage2_model = "claude-sonnet-4-6"
        mock_settings.stage3_model = "claude-opus-4-6"
        mock_settings.coarse_filter_threshold = 0.8
        mock_settings.use_batch_api = False
        mock_settings.adjudication_min_tier = "high"
        mock_settings.biorxiv_request_delay = 0
        mock_settings.europepmc_request_delay = 0
        mock_settings.pubmed_request_delay = 0
        mock_settings.ncbi_api_key = ""
        mock_settings.pubmed_query_mode = "all"
        mock_settings.pubmed_mesh_query = ""
        mock_settings.stage2_fallback_models = "claude-opus-4-6"

        with (
            patch("pipeline.orchestrator._run_ingest", mock_ingest),
            patch("pipeline.orchestrator._run_dedup", mock_dedup),
            patch("pipeline.orchestrator.run_coarse_filter", mock_coarse),
            patch("pipeline.orchestrator._run_fulltext", mock_fulltext),
            patch("pipeline.orchestrator.run_methods_analysis", mock_methods),
            patch("pipeline.orchestrator._run_enrichment", mock_enrich),
            patch("pipeline.orchestrator.run_adjudication", mock_adjudicate),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            stats = await run_daily_pipeline(
                settings=mock_settings, session_factory=session_factory, trigger="manual"
            )

        assert call_order == [
            "ingest",
            "dedup",
            "coarse_filter",
            "fulltext",
            "methods_analysis",
            "enrichment",
            "adjudication",
        ]
        assert stats.finished_at is not None

    async def test_stats_populated(self, db_engine, db_session: AsyncSession):
        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        mock_settings = MagicMock()
        mock_settings.database_url = MagicMock()
        mock_settings.database_url.get_secret_value = MagicMock(
            return_value="sqlite+aiosqlite:///:memory:"
        )
        mock_settings.anthropic_api_key = MagicMock()
        mock_settings.anthropic_api_key.get_secret_value = MagicMock(return_value="sk-test")
        mock_settings.stage1_model = "claude-haiku-4-5-20251001"
        mock_settings.stage2_model = "claude-sonnet-4-6"
        mock_settings.stage3_model = "claude-opus-4-6"
        mock_settings.coarse_filter_threshold = 0.8
        mock_settings.use_batch_api = False
        mock_settings.adjudication_min_tier = "high"
        mock_settings.biorxiv_request_delay = 0
        mock_settings.europepmc_request_delay = 0
        mock_settings.pubmed_request_delay = 0
        mock_settings.ncbi_api_key = ""
        mock_settings.pubmed_query_mode = "all"
        mock_settings.pubmed_mesh_query = ""

        with (
            patch("pipeline.orchestrator._run_ingest", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=([], 0))),
            patch("pipeline.orchestrator.run_coarse_filter", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_fulltext", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            stats = await run_daily_pipeline(
                settings=mock_settings, session_factory=session_factory, trigger="manual"
            )

        assert stats.started_at is not None
        assert stats.finished_at is not None
        assert isinstance(stats.errors, list)
        assert isinstance(stats.total_cost_usd, float)

    async def test_pipeline_run_row_written(self, db_engine, db_session: AsyncSession):
        from pipeline.models import PipelineRun
        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        mock_settings = MagicMock()
        mock_settings.database_url = MagicMock()
        mock_settings.database_url.get_secret_value = MagicMock(
            return_value="sqlite+aiosqlite:///:memory:"
        )
        mock_settings.anthropic_api_key = MagicMock()
        mock_settings.anthropic_api_key.get_secret_value = MagicMock(return_value="sk-test")
        mock_settings.stage1_model = "claude-haiku-4-5-20251001"
        mock_settings.stage2_model = "claude-sonnet-4-6"
        mock_settings.stage3_model = "claude-opus-4-6"
        mock_settings.coarse_filter_threshold = 0.8
        mock_settings.use_batch_api = False
        mock_settings.adjudication_min_tier = "high"
        mock_settings.biorxiv_request_delay = 0
        mock_settings.europepmc_request_delay = 0
        mock_settings.pubmed_request_delay = 0
        mock_settings.ncbi_api_key = ""
        mock_settings.pubmed_query_mode = "all"
        mock_settings.pubmed_mesh_query = ""

        with (
            patch("pipeline.orchestrator._run_ingest", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=([], 0))),
            patch("pipeline.orchestrator.run_coarse_filter", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_fulltext", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            await run_daily_pipeline(
                settings=mock_settings, session_factory=session_factory, trigger="manual"
            )

        # Check PipelineRun row was written
        async with session_factory() as check_session:
            result = await check_session.execute(select(PipelineRun))
            runs = result.scalars().all()
            assert len(runs) == 1
            assert runs[0].trigger == "manual"
            assert runs[0].finished_at is not None

    async def test_stage_failure_isolation(self, db_engine, db_session: AsyncSession):
        """A failure in one stage should not prevent later stages."""
        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        mock_settings = MagicMock()
        mock_settings.database_url = MagicMock()
        mock_settings.database_url.get_secret_value = MagicMock(
            return_value="sqlite+aiosqlite:///:memory:"
        )
        mock_settings.anthropic_api_key = MagicMock()
        mock_settings.anthropic_api_key.get_secret_value = MagicMock(return_value="sk-test")
        mock_settings.stage1_model = "claude-haiku-4-5-20251001"
        mock_settings.stage2_model = "claude-sonnet-4-6"
        mock_settings.stage3_model = "claude-opus-4-6"
        mock_settings.coarse_filter_threshold = 0.8
        mock_settings.use_batch_api = False
        mock_settings.adjudication_min_tier = "high"
        mock_settings.biorxiv_request_delay = 0
        mock_settings.europepmc_request_delay = 0
        mock_settings.pubmed_request_delay = 0
        mock_settings.ncbi_api_key = ""
        mock_settings.pubmed_query_mode = "all"
        mock_settings.pubmed_mesh_query = ""

        async def failing_ingest(session, settings, from_date, to_date):
            raise RuntimeError("Ingest exploded")

        with (
            patch("pipeline.orchestrator._run_ingest", failing_ingest),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=([], 0))),
            patch("pipeline.orchestrator.run_coarse_filter", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_fulltext", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            stats = await run_daily_pipeline(
                settings=mock_settings, session_factory=session_factory, trigger="manual"
            )

        # Pipeline completed despite ingest failure
        assert stats.finished_at is not None
        assert len(stats.errors) >= 1
        assert "Ingest exploded" in stats.errors[0]

    async def test_custom_date_range(self, db_engine, db_session: AsyncSession):
        """Pipeline should use caller-provided from_date and to_date."""
        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        mock_settings = _make_mock_settings()

        captured_dates = {}

        async def capture_ingest(session, settings, from_date, to_date):
            captured_dates["from"] = from_date
            captured_dates["to"] = to_date
            return []

        with (
            patch("pipeline.orchestrator._run_ingest", capture_ingest),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=([], 0))),
            patch("pipeline.orchestrator.run_coarse_filter", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_fulltext", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            await run_daily_pipeline(
                settings=mock_settings,
                session_factory=session_factory,
                trigger="manual",
                from_date=date(2026, 1, 1),
                to_date=date(2026, 1, 15),
            )

        assert captured_dates["from"] == date(2026, 1, 1)
        assert captured_dates["to"] == date(2026, 1, 15)

    async def test_pipeline_run_records_date_range(self, db_engine, db_session: AsyncSession):
        """PipelineRun row should record the from_date and to_date."""
        from pipeline.models import PipelineRun
        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        mock_settings = _make_mock_settings()

        with (
            patch("pipeline.orchestrator._run_ingest", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=([], 0))),
            patch("pipeline.orchestrator.run_coarse_filter", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_fulltext", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            await run_daily_pipeline(
                settings=mock_settings,
                session_factory=session_factory,
                trigger="manual",
                from_date=date(2026, 2, 1),
                to_date=date(2026, 2, 5),
            )

        async with session_factory() as check_session:
            result = await check_session.execute(select(PipelineRun))
            run = result.scalars().first()
            assert run is not None
            assert run.from_date == date(2026, 2, 1)
            assert run.to_date == date(2026, 2, 5)

    async def test_pipeline_run_progress_tracking(self, db_engine, db_session: AsyncSession):
        """PipelineRun row should track paper counts from each stage."""
        from pipeline.models import PipelineRun
        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        mock_settings = _make_mock_settings()

        # Simulate ingest returning 5 papers (as mock Paper objects)
        mock_papers = [MagicMock(id=i) for i in range(5)]

        with (
            patch("pipeline.orchestrator._run_ingest", AsyncMock(return_value=mock_papers)),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=(mock_papers[:3], 2))),
            patch(
                "pipeline.orchestrator.run_coarse_filter",
                AsyncMock(return_value=mock_papers[:2]),
            ),
            patch("pipeline.orchestrator._run_fulltext", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            stats = await run_daily_pipeline(
                settings=mock_settings,
                session_factory=session_factory,
                trigger="manual",
            )

        assert stats.papers_ingested == 5
        assert stats.papers_after_dedup == 3
        assert stats.papers_coarse_passed == 2

        # Verify DB record matches
        async with session_factory() as check_session:
            result = await check_session.execute(select(PipelineRun))
            run = result.scalars().first()
            assert run is not None
            assert run.papers_ingested == 5
            assert run.papers_after_dedup == 3
            assert run.papers_coarse_passed == 2
            assert run.current_stage == "complete"

    async def test_multiple_stage_failures_all_recorded(self, db_engine, db_session: AsyncSession):
        """Errors from multiple stages should all be recorded in stats."""
        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        mock_settings = _make_mock_settings()

        async def failing_ingest(session, settings, from_date, to_date):
            raise ValueError("Ingest failed")

        async def failing_coarse(session, llm_client, papers, use_batch, model, threshold):
            raise RuntimeError("Coarse filter failed")

        with (
            patch("pipeline.orchestrator._run_ingest", failing_ingest),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=([], 0))),
            patch("pipeline.orchestrator.run_coarse_filter", failing_coarse),
            patch("pipeline.orchestrator._run_fulltext", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            stats = await run_daily_pipeline(
                settings=mock_settings,
                session_factory=session_factory,
                trigger="manual",
            )

        assert stats.finished_at is not None
        assert len(stats.errors) >= 2
        error_text = " ".join(stats.errors)
        assert "Ingest failed" in error_text
        assert "Coarse filter failed" in error_text

    async def test_trigger_recorded_in_run(self, db_engine, db_session: AsyncSession):
        """Trigger value should be stored in the PipelineRun record."""
        from pipeline.models import PipelineRun
        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        mock_settings = _make_mock_settings()

        with (
            patch("pipeline.orchestrator._run_ingest", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=([], 0))),
            patch("pipeline.orchestrator.run_coarse_filter", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_fulltext", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            await run_daily_pipeline(
                settings=mock_settings,
                session_factory=session_factory,
                trigger="scheduled",
            )

        async with session_factory() as check_session:
            result = await check_session.execute(select(PipelineRun))
            run = result.scalars().first()
            assert run is not None
            assert run.trigger == "scheduled"

    async def test_default_date_range_is_2_days(self, db_engine, db_session: AsyncSession):
        """When no dates provided, from_date should be 2 days before to_date."""
        from datetime import timedelta

        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        mock_settings = _make_mock_settings()

        captured_dates = {}

        async def capture_ingest(session, settings, from_date, to_date):
            captured_dates["from"] = from_date
            captured_dates["to"] = to_date
            return []

        with (
            patch("pipeline.orchestrator._run_ingest", capture_ingest),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=([], 0))),
            patch("pipeline.orchestrator.run_coarse_filter", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_fulltext", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
        ):
            mock_llm_cls.return_value = AsyncMock()
            await run_daily_pipeline(
                settings=mock_settings,
                session_factory=session_factory,
                trigger="manual",
            )

        # Default to_date is today, from_date is today - 2 days
        assert captured_dates["to"] == date.today()
        assert captured_dates["from"] == date.today() - timedelta(days=2)

    async def test_errors_trigger_alert(self, db_engine, db_session: AsyncSession):
        """Pipeline errors should trigger failure alert at the end."""
        from pipeline.orchestrator import run_daily_pipeline

        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        mock_settings = _make_mock_settings()

        async def failing_ingest(session, settings, from_date, to_date):
            raise RuntimeError("Network timeout")

        with (
            patch("pipeline.orchestrator._run_ingest", failing_ingest),
            patch("pipeline.orchestrator._run_dedup", AsyncMock(return_value=([], 0))),
            patch("pipeline.orchestrator.run_coarse_filter", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator._run_fulltext", AsyncMock()),
            patch("pipeline.orchestrator.run_methods_analysis", AsyncMock()),
            patch("pipeline.orchestrator._run_enrichment", AsyncMock(return_value=[])),
            patch("pipeline.orchestrator.run_adjudication", AsyncMock()),
            patch("pipeline.orchestrator.LLMClient") as mock_llm_cls,
            patch(
                "pipeline.orchestrator.send_pipeline_failure_alert",
                new_callable=AsyncMock,
            ) as mock_alert,
        ):
            mock_llm_cls.return_value = AsyncMock()
            stats = await run_daily_pipeline(
                settings=mock_settings,
                session_factory=session_factory,
                trigger="manual",
            )

        assert len(stats.errors) >= 1
        mock_alert.assert_called_once()
        alert_errors = mock_alert.call_args.kwargs.get("errors") or mock_alert.call_args[0][0]
        assert any("Network timeout" in e for e in alert_errors)
