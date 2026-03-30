"""Daily pipeline orchestrator -- ties all stages together.

Usage:
    stats = await run_daily_pipeline()

Or with custom settings/session:
    stats = await run_daily_pipeline(settings=my_settings, session_factory=my_factory)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pipeline.enrichment.enricher import enrich_paper
from pipeline.fulltext.retriever import retrieve_full_text
from pipeline.ingest.biorxiv import BiorxivClient
from pipeline.ingest.dedup import DedupEngine
from pipeline.ingest.europepmc import EuropepmcClient
from pipeline.ingest.pubmed import PubmedClient
from pipeline.models import Paper, PipelineRun, PipelineStage
from pipeline.triage.adjudication import run_adjudication
from pipeline.triage.coarse_filter import run_coarse_filter
from pipeline.triage.llm import LLMClient
from pipeline.triage.methods_analysis import run_methods_analysis

log = structlog.get_logger()


@dataclass
class PipelineRunStats:
    """Statistics from a single pipeline run."""

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    papers_ingested: int = 0
    papers_after_dedup: int = 0
    papers_coarse_passed: int = 0
    papers_fulltext_retrieved: int = 0
    papers_methods_analysed: int = 0
    papers_enriched: int = 0
    papers_adjudicated: int = 0
    errors: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0


async def run_daily_pipeline(
    settings=None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    trigger: str = "manual",
) -> PipelineRunStats:
    """Run the complete daily triage pipeline.

    Args:
        settings: Pipeline settings. If None, loads from environment.
        session_factory: SQLAlchemy async session factory. If None, creates one.
        trigger: "scheduled" or "manual" -- recorded in PipelineRun.
    """
    if settings is None:
        from pipeline.config import get_settings

        settings = get_settings()

    if session_factory is None:
        from pipeline.db import make_engine, make_session_factory

        engine = make_engine(settings.database_url.get_secret_value())
        session_factory = make_session_factory(engine)

    stats = PipelineRunStats()
    llm_client = LLMClient(api_key=settings.anthropic_api_key.get_secret_value())

    # Create PipelineRun record
    run_record = PipelineRun(
        started_at=stats.started_at,
        trigger=trigger,
    )
    async with session_factory() as session:
        session.add(run_record)
        await session.commit()
    run_id = run_record.id

    # Date range: last 2 days
    to_date = date.today()
    from_date = to_date - timedelta(days=2)

    async with session_factory() as session:
        # Stage 1: Ingest
        ingested_papers: list[Paper] = []
        try:
            ingested_papers = await _run_ingest(session, settings, from_date, to_date)
            stats.papers_ingested = len(ingested_papers)
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Ingest: {exc}")
            log.error("pipeline_ingest_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 2: Dedup
        non_dup_papers: list[Paper] = []
        try:
            non_dup_papers, dup_count = await _run_dedup(session, ingested_papers)
            stats.papers_after_dedup = len(non_dup_papers)
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Dedup: {exc}")
            log.error("pipeline_dedup_error", error=str(exc), exc_info=True)
            non_dup_papers = ingested_papers
            await session.rollback()

    async with session_factory() as session:
        # Stage 3: Coarse filter
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.INGESTED,
                Paper.is_duplicate_of.is_(None),
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            ingested = result.scalars().all()

            passed = await run_coarse_filter(
                session=session,
                llm_client=llm_client,
                papers=list(ingested),
                use_batch=settings.use_batch_api,
                model=settings.stage1_model,
                threshold=settings.coarse_filter_threshold,
            )
            stats.papers_coarse_passed = len(passed)
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Coarse filter: {exc}")
            log.error("pipeline_coarse_filter_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 4: Full-text retrieval
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.COARSE_FILTERED,
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            coarse_passed = list(result.scalars().all())

            await _run_fulltext(session, coarse_passed, settings)
            stats.papers_fulltext_retrieved = sum(
                1 for p in coarse_passed if p.full_text_retrieved
            )
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Full-text retrieval: {exc}")
            log.error("pipeline_fulltext_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 5: Methods analysis
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.FULLTEXT_RETRIEVED,
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            fulltext_papers = list(result.scalars().all())

            await run_methods_analysis(
                session=session,
                llm_client=llm_client,
                papers=fulltext_papers,
                use_batch=settings.use_batch_api,
                model=settings.stage2_model,
            )
            stats.papers_methods_analysed = len(fulltext_papers)
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Methods analysis: {exc}")
            log.error("pipeline_methods_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 6: Enrichment
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.METHODS_ANALYSED,
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            methods_papers = list(result.scalars().all())

            enriched = await _run_enrichment(session, methods_papers, settings)
            stats.papers_enriched = len(enriched)
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Enrichment: {exc}")
            log.error("pipeline_enrichment_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 7: Adjudication
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.METHODS_ANALYSED,
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            to_adjudicate = list(result.scalars().all())

            await run_adjudication(
                session=session,
                llm_client=llm_client,
                papers=to_adjudicate,
                model=settings.stage3_model,
                min_tier=settings.adjudication_min_tier,
            )
            stats.papers_adjudicated = len(to_adjudicate)
            await session.commit()
        except Exception as exc:
            stats.errors.append(f"Adjudication: {exc}")
            log.error("pipeline_adjudication_error", error=str(exc), exc_info=True)
            await session.rollback()

    stats.finished_at = datetime.now(UTC)

    # Update PipelineRun record
    async with session_factory() as session:
        stmt = select(PipelineRun).where(PipelineRun.id == run_id)
        result = await session.execute(stmt)
        run_record = result.scalar_one()
        run_record.finished_at = stats.finished_at
        run_record.papers_ingested = stats.papers_ingested
        run_record.papers_after_dedup = stats.papers_after_dedup
        run_record.papers_coarse_passed = stats.papers_coarse_passed
        run_record.papers_fulltext_retrieved = stats.papers_fulltext_retrieved
        run_record.papers_methods_analysed = stats.papers_methods_analysed
        run_record.papers_enriched = stats.papers_enriched
        run_record.papers_adjudicated = stats.papers_adjudicated
        run_record.errors = stats.errors if stats.errors else None
        run_record.total_cost_usd = stats.total_cost_usd
        await session.commit()

    log.info(
        "pipeline_complete",
        papers_ingested=stats.papers_ingested,
        papers_adjudicated=stats.papers_adjudicated,
        errors=len(stats.errors),
        duration_s=(stats.finished_at - stats.started_at).total_seconds(),
    )

    return stats


async def _run_ingest(
    session: AsyncSession,
    settings,
    from_date: date,
    to_date: date,
) -> list[Paper]:
    """Run all ingest clients and return new papers."""
    papers: list[Paper] = []

    # bioRxiv
    async with BiorxivClient(
        server="biorxiv", request_delay=settings.biorxiv_request_delay
    ) as client:
        async for record in client.fetch_papers(from_date, to_date):
            paper = Paper(**{k: v for k, v in record.items() if k != "full_text_url"})
            if record.get("full_text_url"):
                paper.full_text_url = record["full_text_url"]
            session.add(paper)
            papers.append(paper)

    # medRxiv
    async with BiorxivClient(
        server="medrxiv", request_delay=settings.biorxiv_request_delay
    ) as client:
        async for record in client.fetch_papers(from_date, to_date):
            paper = Paper(**{k: v for k, v in record.items() if k != "full_text_url"})
            if record.get("full_text_url"):
                paper.full_text_url = record["full_text_url"]
            session.add(paper)
            papers.append(paper)

    # Europe PMC
    async with EuropepmcClient(
        request_delay=settings.europepmc_request_delay,
    ) as client:
        async for record in client.fetch_papers(from_date, to_date):
            paper = Paper(**{k: v for k, v in record.items() if k != "full_text_url"})
            if record.get("full_text_url"):
                paper.full_text_url = record["full_text_url"]
            session.add(paper)
            papers.append(paper)

    # PubMed
    async with PubmedClient(
        api_key=settings.ncbi_api_key,
        request_delay=settings.pubmed_request_delay,
        query_mode=settings.pubmed_query_mode,
        mesh_query=settings.pubmed_mesh_query,
    ) as client:
        async for record in client.fetch_papers(from_date, to_date):
            paper = Paper(**{k: v for k, v in record.items() if k != "full_text_url"})
            if record.get("full_text_url"):
                paper.full_text_url = record["full_text_url"]
            session.add(paper)
            papers.append(paper)

    await session.flush()
    log.info("ingest_complete", count=len(papers))
    return papers


async def _run_fulltext(
    session: AsyncSession,
    papers: list[Paper],
    settings,
) -> None:
    """Run full-text retrieval for each paper."""
    for paper in papers:
        await retrieve_full_text(session, paper, settings)
    await session.flush()
    log.info("fulltext_stage_complete", total=len(papers))


async def _run_dedup(
    session: AsyncSession,
    papers: list[Paper],
) -> tuple[list[Paper], int]:
    """Run dedup on new papers. Returns (non_duplicates, duplicate_count)."""
    engine = DedupEngine(session)
    non_dups: list[Paper] = []
    dup_count = 0

    for paper in papers:
        record = {
            "doi": paper.doi,
            "title": paper.title,
            "authors": paper.authors,
            "posted_date": paper.posted_date,
        }
        result = await engine.check(record)
        if result.is_duplicate:
            paper.is_duplicate_of = result.duplicate_of
            await engine.record_duplicate(
                canonical_id=result.duplicate_of,
                member_id=paper.id,
                result=result,
            )
            dup_count += 1
        else:
            non_dups.append(paper)

    await session.flush()
    log.info("dedup_complete", total=len(papers), duplicates=dup_count)
    return non_dups, dup_count


async def _run_enrichment(
    session: AsyncSession,
    papers: list[Paper],
    settings,
) -> list[Paper]:
    """Run enrichment on papers and store results."""
    enriched: list[Paper] = []

    for paper in papers:
        try:
            result = await enrich_paper(paper, settings)
            paper.enrichment_data = {
                **result.data,
                "_meta": {
                    "sources_succeeded": result.sources_succeeded,
                    "sources_failed": result.sources_failed,
                    "fetched_at": datetime.now(UTC).isoformat(),
                },
            }
            enriched.append(paper)
        except Exception as exc:
            log.warning("enrichment_paper_error", paper_id=str(paper.id), error=str(exc))

    await session.flush()
    log.info("enrichment_stage_complete", total=len(papers), enriched=len(enriched))
    return enriched
