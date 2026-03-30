"""Tests for pipeline.scheduler -- APScheduler wrapper for daily pipeline runs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


class TestPipelineScheduler:
    """Tests for PipelineScheduler."""

    def _make_settings(self):
        mock_settings = MagicMock()
        mock_settings.daily_run_hour = 6
        mock_settings.database_url = MagicMock()
        mock_settings.database_url.get_secret_value = MagicMock(
            return_value="sqlite+aiosqlite:///:memory:"
        )
        mock_settings.anthropic_api_key = MagicMock()
        mock_settings.anthropic_api_key.get_secret_value = MagicMock(
            return_value="sk-test"
        )
        return mock_settings

    def test_scheduler_creates_job(self):
        """Scheduler initialises with a cron job at the configured hour."""
        from pipeline.scheduler import PipelineScheduler

        settings = self._make_settings()
        scheduler = PipelineScheduler(settings)

        assert scheduler._settings.daily_run_hour == 6
        assert scheduler._paused is False

    async def test_get_status_before_start(self):
        from pipeline.scheduler import PipelineScheduler

        settings = self._make_settings()
        scheduler = PipelineScheduler(settings)

        status = scheduler.get_status()
        assert status["running"] is False
        assert status["paused"] is False
        assert status["last_run_stats"] is None

    async def test_trigger_run_executes(self):
        from pipeline.scheduler import PipelineScheduler

        settings = self._make_settings()
        scheduler = PipelineScheduler(settings)

        mock_stats = MagicMock()
        with patch(
            "pipeline.scheduler.run_daily_pipeline",
            new_callable=AsyncMock,
            return_value=mock_stats,
        ):
            stats = await scheduler.trigger_run()

        assert stats is mock_stats
        assert scheduler._last_run_stats is mock_stats

    async def test_update_schedule_changes_hour(self):
        from pipeline.scheduler import PipelineScheduler

        settings = self._make_settings()
        scheduler = PipelineScheduler(settings)

        await scheduler.update_schedule(12, 30)
        assert scheduler._hour == 12
        assert scheduler._minute == 30

    async def test_pause_and_resume(self):
        from pipeline.scheduler import PipelineScheduler

        settings = self._make_settings()
        scheduler = PipelineScheduler(settings)

        await scheduler.pause()
        assert scheduler._paused is True
        status = scheduler.get_status()
        assert status["paused"] is True

        await scheduler.resume()
        assert scheduler._paused is False
        status = scheduler.get_status()
        assert status["paused"] is False

    async def test_get_status_after_run(self):
        from pipeline.scheduler import PipelineScheduler

        settings = self._make_settings()
        scheduler = PipelineScheduler(settings)

        mock_stats = MagicMock()
        with patch(
            "pipeline.scheduler.run_daily_pipeline",
            new_callable=AsyncMock,
            return_value=mock_stats,
        ):
            await scheduler.trigger_run()

        status = scheduler.get_status()
        assert status["last_run_stats"] is mock_stats
