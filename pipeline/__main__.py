"""Entry point for the DURC triage pipeline.

Usage:
    python -m pipeline              # One-shot run
    python -m pipeline --schedule   # Long-lived scheduled mode
"""

from __future__ import annotations

import asyncio
import sys

import structlog

log = structlog.get_logger()


def main() -> None:
    """Parse args and run the pipeline in the appropriate mode."""
    if "--schedule" in sys.argv:
        _run_scheduled()
    else:
        _run_oneshot()


def _run_oneshot() -> None:
    """Execute a single pipeline run and exit."""
    from pipeline.orchestrator import run_daily_pipeline

    log.info("pipeline_oneshot_start")
    stats = asyncio.run(run_daily_pipeline(trigger="manual"))
    log.info(
        "pipeline_oneshot_complete",
        papers_ingested=stats.papers_ingested,
        papers_adjudicated=stats.papers_adjudicated,
        errors=len(stats.errors),
    )
    if stats.errors:
        log.warning("pipeline_errors", errors=stats.errors)


def _run_scheduled() -> None:
    """Start the scheduler for continuous daily operation."""
    from pipeline.config import get_settings
    from pipeline.scheduler import PipelineScheduler

    settings = get_settings()
    scheduler = PipelineScheduler(settings)
    log.info("pipeline_scheduled_start", hour=settings.daily_run_hour)
    asyncio.run(scheduler.start())


if __name__ == "__main__":
    main()
