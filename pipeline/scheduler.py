"""APScheduler 3.x wrapper for daily pipeline execution.

Usage:
    scheduler = PipelineScheduler(settings)
    await scheduler.start()  # Blocks forever, runs daily

Or for programmatic control:
    scheduler = PipelineScheduler(settings)
    stats = await scheduler.trigger_run()  # One-shot
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from pipeline.orchestrator import PipelineRunStats, run_daily_pipeline

log = structlog.get_logger()


class PipelineScheduler:
    """Manages scheduled and on-demand pipeline runs."""

    def __init__(self, settings) -> None:
        self._settings = settings
        self._hour = settings.daily_run_hour
        self._minute = 0
        self._scheduler: AsyncIOScheduler | None = None
        self._paused = False
        self._running = False
        self._last_run_stats: PipelineRunStats | None = None
        self._last_run_time: datetime | None = None

    async def start(self) -> None:
        """Start the scheduler with the configured daily cron. Blocks forever."""
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._run_pipeline,
            trigger=CronTrigger(hour=self._hour, minute=self._minute),
            id="daily_pipeline",
            replace_existing=True,
        )
        self._scheduler.start()
        self._running = True
        log.info(
            "scheduler_started",
            hour=self._hour,
            minute=self._minute,
        )

        # Block forever (until stop is called or process exits)
        try:
            while self._running:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            await self.stop()

    async def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        self._running = False
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        log.info("scheduler_stopped")

    async def trigger_run(self) -> PipelineRunStats:
        """Trigger an immediate pipeline run."""
        log.info("manual_run_triggered")
        stats = await self._run_pipeline(trigger="manual")
        return stats

    async def update_schedule(self, hour: int, minute: int = 0) -> None:
        """Change the daily run time."""
        self._hour = hour
        self._minute = minute
        if self._scheduler:
            self._scheduler.reschedule_job(
                "daily_pipeline",
                trigger=CronTrigger(hour=hour, minute=minute),
            )
        log.info("schedule_updated", hour=hour, minute=minute)

    async def pause(self) -> None:
        """Pause scheduled runs (manual runs still allowed)."""
        self._paused = True
        if self._scheduler:
            self._scheduler.pause_job("daily_pipeline")
        log.info("scheduler_paused")

    async def resume(self) -> None:
        """Resume scheduled runs."""
        self._paused = False
        if self._scheduler:
            self._scheduler.resume_job("daily_pipeline")
        log.info("scheduler_resumed")

    def get_status(self) -> dict:
        """Return scheduler state for the dashboard."""
        next_run = None
        if self._scheduler and not self._paused:
            job = self._scheduler.get_job("daily_pipeline")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()

        return {
            "running": self._running,
            "paused": self._paused,
            "next_run_time": next_run,
            "last_run_time": self._last_run_time.isoformat() if self._last_run_time else None,
            "last_run_stats": self._last_run_stats,
        }

    async def _run_pipeline(self, trigger: str = "scheduled") -> PipelineRunStats:
        """Execute the pipeline and update internal state."""
        self._last_run_time = datetime.now(UTC)
        try:
            stats = await run_daily_pipeline(
                settings=self._settings,
                trigger=trigger,
            )
            self._last_run_stats = stats
            log.info(
                "pipeline_run_complete",
                trigger=trigger,
                papers_ingested=stats.papers_ingested,
                errors=len(stats.errors),
            )
            return stats
        except Exception as exc:
            log.error("pipeline_run_failed", trigger=trigger, error=str(exc), exc_info=True)
            error_stats = PipelineRunStats()
            error_stats.errors = [str(exc)]
            error_stats.finished_at = datetime.now(UTC)
            self._last_run_stats = error_stats
            return error_stats
