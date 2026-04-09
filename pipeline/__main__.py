"""Entry point for the DURC triage pipeline.

Usage:
    python -m pipeline              # One-shot run (last 2 days)
    python -m pipeline --schedule   # Long-lived scheduled mode
    python -m pipeline --from-date 2026-03-01 --to-date 2026-03-31  # Backfill
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

import structlog

log = structlog.get_logger()


def parse_date(s: str) -> date:
    """Parse YYYY-MM-DD string to date."""
    return date.fromisoformat(s)


def main() -> None:
    """Parse args and run the pipeline in the appropriate mode."""
    parser = argparse.ArgumentParser(description="DURC triage pipeline")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run in long-lived scheduled mode (daily cron + HTTP API)",
    )
    parser.add_argument(
        "--from-date",
        type=parse_date,
        default=None,
        help="Start date for ingestion (YYYY-MM-DD). Default: 2 days ago.",
    )
    parser.add_argument(
        "--to-date",
        type=parse_date,
        default=None,
        help="End date for ingestion (YYYY-MM-DD). Default: today.",
    )
    parser.add_argument(
        "--pubmed-query-mode",
        choices=["all", "mesh_filtered"],
        default=None,
        help="PubMed query mode. Overrides config setting.",
    )
    parser.add_argument(
        "--skip-backlog",
        action="store_true",
        help="Only process papers within the date range; skip backlog from previous runs.",
    )
    args = parser.parse_args()

    if args.schedule:
        _run_scheduled()
    else:
        _run_oneshot(
            from_date=args.from_date,
            to_date=args.to_date,
            pubmed_query_mode=args.pubmed_query_mode,
            include_backlog=not args.skip_backlog,
        )


def _run_oneshot(
    from_date: date | None = None,
    to_date: date | None = None,
    pubmed_query_mode: str | None = None,
    include_backlog: bool = True,
) -> None:
    """Execute a single pipeline run and exit."""
    from pipeline.orchestrator import run_daily_pipeline

    log.info(
        "pipeline_oneshot_start",
        from_date=str(from_date) if from_date else "default",
        to_date=str(to_date) if to_date else "default",
        pubmed_query_mode=pubmed_query_mode or "config default",
        include_backlog=include_backlog,
    )
    stats = asyncio.run(
        run_daily_pipeline(
            trigger="manual",
            from_date=from_date,
            to_date=to_date,
            pubmed_query_mode_override=pubmed_query_mode,
            include_backlog=include_backlog,
        )
    )
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
