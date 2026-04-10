"""Daily pipeline orchestrator -- ties all stages together.

Usage:
    stats = await run_daily_pipeline()

Or with custom settings/session:
    stats = await run_daily_pipeline(settings=my_settings, session_factory=my_factory)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pipeline.enrichment.enricher import enrich_paper
from pipeline.fulltext.retriever import fetch_full_text_content
from pipeline.ingest.arxiv import ArxivClient
from pipeline.ingest.biorxiv import BiorxivClient
from pipeline.ingest.crossref import CrossrefClient
from pipeline.ingest.dedup import DedupEngine
from pipeline.ingest.europepmc import EuropepmcClient
from pipeline.ingest.pubmed import PubmedClient
from pipeline.ingest.zenodo import ZenodoClient
from pipeline.models import Paper, PipelineRun, PipelineStage
from pipeline.triage.adjudication import run_adjudication
from pipeline.triage.coarse_filter import run_coarse_filter
from pipeline.triage.llm import LLMClient
from pipeline.triage.methods_analysis import run_methods_analysis

log = structlog.get_logger()


def _exc_str(exc: Exception) -> str:
    """Format an exception for error logging. Includes class name so
    exceptions with empty str() (e.g. httpx.ReadTimeout) are still useful."""
    msg = str(exc)
    name = type(exc).__name__
    return f"{name}: {msg}" if msg else name


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
    # Per-stage counts of papers picked up from previous runs (backlog)
    backlog: dict[str, int] = field(default_factory=dict)


async def run_daily_pipeline(
    settings=None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    trigger: str = "manual",
    from_date: date | None = None,
    to_date: date | None = None,
    pubmed_query_mode_override: str | None = None,
    include_backlog: bool = True,
) -> PipelineRunStats:
    """Run the complete daily triage pipeline.

    Args:
        settings: Pipeline settings. If None, loads from environment.
        session_factory: SQLAlchemy async session factory. If None, creates one.
        trigger: "scheduled" or "manual" -- recorded in PipelineRun.
        pubmed_query_mode_override: If set, overrides settings.pubmed_query_mode.
        include_backlog: If False, only process papers with posted_date within
            the run's date range — skip backlog from previous runs.
    """
    if settings is None:
        from pipeline.config import get_settings

        settings = get_settings()

    if pubmed_query_mode_override:
        settings.pubmed_query_mode = pubmed_query_mode_override

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
        pubmed_query_mode=settings.pubmed_query_mode,
        pid=os.getpid(),
    )
    async with session_factory() as session:
        session.add(run_record)
        await session.commit()
    run_id = run_record.id

    current_stage = "starting"

    async def _flush_progress() -> None:
        """Write current stats to DB so the dashboard can poll progress."""
        async with session_factory() as s:
            stmt = select(PipelineRun).where(PipelineRun.id == run_id)
            rec = (await s.execute(stmt)).scalar_one()
            rec.current_stage = current_stage
            rec.papers_ingested = stats.papers_ingested
            rec.papers_after_dedup = stats.papers_after_dedup
            rec.papers_coarse_passed = stats.papers_coarse_passed
            rec.papers_fulltext_retrieved = stats.papers_fulltext_retrieved
            rec.papers_methods_analysed = stats.papers_methods_analysed
            rec.papers_enriched = stats.papers_enriched
            rec.papers_adjudicated = stats.papers_adjudicated
            rec.errors = stats.errors if stats.errors else None
            rec.total_cost_usd = stats.total_cost_usd
            rec.backlog_stats = stats.backlog if stats.backlog else None
            await s.commit()

    await _flush_progress()

    # Date range: use caller-provided dates or default to last 2 days
    if to_date is None:
        to_date = date.today()
    if from_date is None:
        from_date = to_date - timedelta(days=2)

    # Store resolved date range on the run record
    async with session_factory() as s:
        stmt = select(PipelineRun).where(PipelineRun.id == run_id)
        rec = (await s.execute(stmt)).scalar_one()
        rec.from_date = from_date
        rec.to_date = to_date
        await s.commit()

    log.info(
        "pipeline_started",
        from_date=str(from_date),
        to_date=str(to_date),
        trigger=trigger,
        include_backlog=include_backlog,
    )

    # When skipping backlog, restrict stage queries to the run's date range
    def _date_filter():
        """Return SQLAlchemy filter clauses to restrict to the run's date range."""
        if include_backlog:
            return []
        return [Paper.posted_date >= from_date, Paper.posted_date <= to_date]

    async with session_factory() as session:
        # Stage 1: Ingest
        current_stage = "ingest"
        await _flush_progress()
        log.info("stage_starting", stage="ingest", description="Fetching papers from data sources")
        ingested_papers: list[Paper] = []
        try:
            ingested_papers = await _run_ingest(session, settings, from_date, to_date)
            stats.papers_ingested = len(ingested_papers)
            await session.commit()
            await _flush_progress()
            log.info("stage_complete", stage="ingest", papers=len(ingested_papers))
        except Exception as exc:
            stats.errors.append(f"Ingest: {_exc_str(exc)}")
            log.error("pipeline_ingest_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 2: Dedup
        current_stage = "dedup"
        await _flush_progress()
        log.info("stage_starting", stage="dedup", papers_to_process=len(ingested_papers))
        non_dup_papers: list[Paper] = []
        try:
            non_dup_papers, dup_count = await _run_dedup(session, ingested_papers, settings)
            stats.papers_after_dedup = len(non_dup_papers)
            await session.commit()
            await _flush_progress()
            log.info(
                "stage_complete",
                stage="dedup",
                unique=len(non_dup_papers),
                duplicates=dup_count,
            )
        except Exception as exc:
            stats.errors.append(f"Dedup: {_exc_str(exc)}")
            log.error("pipeline_dedup_error", error=str(exc), exc_info=True)
            non_dup_papers = ingested_papers
            await session.rollback()

    async with session_factory() as session:
        # Stage 2b: Translate non-English papers
        current_stage = "translation"
        await _flush_progress()
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.INGESTED,
                Paper.is_duplicate_of.is_(None),
                Paper.language.isnot(None),
                Paper.language != "eng",
            )
            result = await session.execute(stmt)
            non_english = list(result.scalars().all())

            if non_english:
                log.info("stage_starting", stage="translation", papers_to_process=len(non_english))
                await _run_translation(session, llm_client, non_english, settings.stage1_model)
                await session.commit()
                await _flush_progress()
                log.info("stage_complete", stage="translation", total=len(non_english))
        except Exception as exc:
            stats.errors.append(f"Translation: {_exc_str(exc)}")
            log.error("pipeline_translation_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 3: Coarse filter
        current_stage = "coarse_filter"
        await _flush_progress()
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.INGESTED,
                Paper.is_duplicate_of.is_(None),
                *_date_filter(),
            )
            result = await session.execute(stmt)
            ingested = result.scalars().all()

            # Skip papers with no usable content (no title or abstract to classify)
            papers_list = []
            skipped = 0
            for p in ingested:
                _not_available = (
                    "",
                    "[Not Available].",
                    "[Not Available]",
                )
                has_title = p.title and p.title.strip() not in _not_available
                has_abstract = p.abstract and p.abstract.strip()
                if has_title or has_abstract:
                    papers_list.append(p)
                else:
                    skipped += 1

            if skipped:
                log.info("coarse_filter_skipped_empty", skipped=skipped)
            backlog = sum(1 for p in papers_list if p.posted_date < from_date or p.posted_date > to_date)
            if backlog:
                stats.backlog["coarse_filter"] = backlog
            log.info("stage_starting", stage="coarse_filter", papers_to_process=len(papers_list), backlog=backlog)
            passed = await run_coarse_filter(
                session=session,
                llm_client=llm_client,
                papers=papers_list,
                use_batch=settings.use_batch_api,
                model=settings.stage1_model,
                threshold=settings.coarse_filter_threshold,
            )
            stats.papers_coarse_passed = len(passed)
            await session.commit()
            await _flush_progress()
            log.info(
                "stage_complete",
                stage="coarse_filter",
                total=len(papers_list),
                passed=len(passed),
            )
        except Exception as exc:
            stats.errors.append(f"Coarse filter: {_exc_str(exc)}")
            log.error("pipeline_coarse_filter_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 4: Full-text retrieval
        current_stage = "fulltext"
        await _flush_progress()
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.COARSE_FILTERED,
                Paper.coarse_filter_passed.is_(True),
                *_date_filter(),
            )
            result = await session.execute(stmt)
            coarse_passed = list(result.scalars().all())

            backlog = sum(1 for p in coarse_passed if p.posted_date < from_date or p.posted_date > to_date)
            if backlog:
                stats.backlog["fulltext"] = backlog
            log.info(
                "stage_starting",
                stage="fulltext_retrieval",
                papers_to_process=len(coarse_passed),
                backlog=backlog,
            )
            await _run_fulltext(session, coarse_passed, settings)
            stats.papers_fulltext_retrieved = sum(1 for p in coarse_passed if p.full_text_retrieved)
            await session.commit()
            await _flush_progress()
            log.info(
                "stage_complete",
                stage="fulltext_retrieval",
                total=len(coarse_passed),
                retrieved=stats.papers_fulltext_retrieved,
            )
        except Exception as exc:
            stats.errors.append(f"Full-text retrieval: {_exc_str(exc)}")
            log.error("pipeline_fulltext_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 4b: Translate non-English methods sections
        current_stage = "fulltext_translation"
        await _flush_progress()
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.FULLTEXT_RETRIEVED,
                Paper.full_text_retrieved.is_(True),
                Paper.language.isnot(None),
                Paper.language != "eng",
                *_date_filter(),
            )
            result = await session.execute(stmt)
            non_english_ft = list(result.scalars().all())

            if non_english_ft:
                log.info(
                    "stage_starting",
                    stage="fulltext_translation",
                    papers_to_process=len(non_english_ft),
                )
                await _run_fulltext_translation(
                    session,
                    llm_client,
                    non_english_ft,
                    settings.stage1_model,
                )
                await session.commit()
                await _flush_progress()
                log.info("stage_complete", stage="fulltext_translation", total=len(non_english_ft))
        except Exception as exc:
            stats.errors.append(f"Fulltext translation: {_exc_str(exc)}")
            log.error("pipeline_fulltext_translation_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 5: Methods analysis
        current_stage = "methods_analysis"
        await _flush_progress()
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.FULLTEXT_RETRIEVED,
                *_date_filter(),
            )
            result = await session.execute(stmt)
            fulltext_papers = list(result.scalars().all())

            backlog = sum(1 for p in fulltext_papers if p.posted_date < from_date or p.posted_date > to_date)
            if backlog:
                stats.backlog["methods_analysis"] = backlog
            log.info(
                "stage_starting",
                stage="methods_analysis",
                papers_to_process=len(fulltext_papers),
                backlog=backlog,
            )
            fallback_models = [
                m.strip()
                for m in settings.stage2_fallback_models.split(",")
                if m.strip()
            ]
            await run_methods_analysis(
                session=session,
                llm_client=llm_client,
                papers=fulltext_papers,
                use_batch=settings.use_batch_api,
                model=settings.stage2_model,
                fallback_models=fallback_models,
            )
            stats.papers_methods_analysed = sum(
                1 for p in fulltext_papers if p.risk_tier is not None
            )
            await session.commit()
            await _flush_progress()
            log.info("stage_complete", stage="methods_analysis", total=len(fulltext_papers))
        except Exception as exc:
            stats.errors.append(f"Methods analysis: {_exc_str(exc)}")
            log.error("pipeline_methods_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 6: Enrichment
        current_stage = "enrichment"
        await _flush_progress()
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.METHODS_ANALYSED,
                *_date_filter(),
            )
            result = await session.execute(stmt)
            methods_papers = list(result.scalars().all())

            backlog = sum(1 for p in methods_papers if p.posted_date < from_date or p.posted_date > to_date)
            if backlog:
                stats.backlog["enrichment"] = backlog
            log.info("stage_starting", stage="enrichment", papers_to_process=len(methods_papers), backlog=backlog)
            enriched = await _run_enrichment(session, methods_papers, settings)
            stats.papers_enriched = len(enriched)
            await session.commit()
            await _flush_progress()
            log.info(
                "stage_complete",
                stage="enrichment",
                total=len(methods_papers),
                enriched=len(enriched),
            )
        except Exception as exc:
            stats.errors.append(f"Enrichment: {_exc_str(exc)}")
            log.error("pipeline_enrichment_error", error=str(exc), exc_info=True)
            await session.rollback()

    async with session_factory() as session:
        # Stage 7: Adjudication
        current_stage = "adjudication"
        await _flush_progress()
        try:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.METHODS_ANALYSED,
                *_date_filter(),
            )
            result = await session.execute(stmt)
            to_adjudicate = list(result.scalars().all())

            backlog = sum(1 for p in to_adjudicate if p.posted_date < from_date or p.posted_date > to_date)
            if backlog:
                stats.backlog["adjudication"] = backlog
            log.info("stage_starting", stage="adjudication", papers_to_process=len(to_adjudicate), backlog=backlog)
            await run_adjudication(
                session=session,
                llm_client=llm_client,
                papers=to_adjudicate,
                model=settings.stage3_model,
                min_tier=settings.adjudication_min_tier,
            )
            stats.papers_adjudicated = len(to_adjudicate)
            await session.commit()
            await _flush_progress()
            log.info("stage_complete", stage="adjudication", total=len(to_adjudicate))
        except Exception as exc:
            stats.errors.append(f"Adjudication: {_exc_str(exc)}")
            log.error("pipeline_adjudication_error", error=str(exc), exc_info=True)
            await session.rollback()

    stats.finished_at = datetime.now(UTC)
    current_stage = "complete"

    # Update PipelineRun record
    async with session_factory() as session:
        stmt = select(PipelineRun).where(PipelineRun.id == run_id)
        result = await session.execute(stmt)
        run_record = result.scalar_one()
        run_record.finished_at = stats.finished_at
        run_record.current_stage = current_stage
        run_record.papers_ingested = stats.papers_ingested
        run_record.papers_after_dedup = stats.papers_after_dedup
        run_record.papers_coarse_passed = stats.papers_coarse_passed
        run_record.papers_fulltext_retrieved = stats.papers_fulltext_retrieved
        run_record.papers_methods_analysed = stats.papers_methods_analysed
        run_record.papers_enriched = stats.papers_enriched
        run_record.papers_adjudicated = stats.papers_adjudicated
        run_record.errors = stats.errors if stats.errors else None
        run_record.total_cost_usd = stats.total_cost_usd
        run_record.backlog_stats = stats.backlog if stats.backlog else None
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
    """Run all ingest clients and return new papers.

    Skips papers whose DOI or title already exists in the DB to avoid
    wasteful re-ingestion on overlapping date ranges.
    """
    # Pre-load existing DOIs and titles so we can skip papers we already
    # have, without a per-paper DB round-trip.  We check ALL existing papers,
    # not just those in the date range, because the same paper can appear
    # from different sources with different posted dates.
    existing_stmt = select(Paper.doi, Paper.title)
    existing_rows = (await session.execute(existing_stmt)).all()
    existing_dois: set[str] = {r.doi.lower() for r in existing_rows if r.doi}
    existing_titles: set[str] = {r.title.lower().strip() for r in existing_rows if r.title}
    log.info(
        "ingest_existing_loaded",
        dois=len(existing_dois),
        titles=len(existing_titles),
    )

    papers: list[Paper] = []

    sources = [
        (
            "biorxiv",
            lambda: BiorxivClient(
                server="biorxiv",
                request_delay=settings.biorxiv_request_delay,
            ),
        ),
        (
            "medrxiv",
            lambda: BiorxivClient(
                server="medrxiv",
                request_delay=settings.biorxiv_request_delay,
            ),
        ),
        ("europepmc", lambda: EuropepmcClient(request_delay=settings.europepmc_request_delay)),
        (
            "pubmed",
            lambda: PubmedClient(
                api_key=settings.ncbi_api_key,
                request_delay=settings.pubmed_request_delay,
                query_mode=settings.pubmed_query_mode,
                mesh_query=settings.pubmed_mesh_query,
            ),
        ),
        (
            "arxiv",
            lambda: ArxivClient(
                request_delay=settings.arxiv_request_delay,
            ),
        ),
        (
            "crossref",
            lambda: CrossrefClient(
                email=settings.crossref_email,
                request_delay=settings.crossref_request_delay,
            ),
        ),
        (
            "zenodo",
            lambda: ZenodoClient(
                request_delay=settings.zenodo_request_delay,
            ),
        ),
    ]

    _extra_keys = {"full_text_url", "_language", "_vernacular_title"}

    for source_name, client_factory in sources:
        source_count = 0
        skipped = 0
        log.info("ingest_source_starting", source=source_name)
        async with client_factory() as client:
            async for record in client.fetch_papers(from_date, to_date):
                # Skip if we already have this paper (by DOI or exact title)
                doi = record.get("doi")
                title = record.get("title")
                if doi and doi.lower() in existing_dois:
                    skipped += 1
                    continue
                if title and title.lower().strip() in existing_titles:
                    skipped += 1
                    continue

                paper = Paper(**{k: v for k, v in record.items() if k not in _extra_keys})
                if record.get("full_text_url"):
                    paper.full_text_url = record["full_text_url"]
                if record.get("_language"):
                    paper.language = record["_language"]
                if record.get("_vernacular_title"):
                    paper.original_title = record["_vernacular_title"]
                session.add(paper)
                papers.append(paper)
                source_count += 1

                # Track the new paper so later sources don't duplicate it
                if doi:
                    existing_dois.add(doi.lower())
                if title:
                    existing_titles.add(title.lower().strip())

        log.info("ingest_source_complete", source=source_name, new=source_count, skipped=skipped)

    await session.flush()
    log.info("ingest_complete", new=len(papers))
    return papers


async def _run_fulltext(
    session: AsyncSession,
    papers: list[Paper],
    settings,
    concurrency: int = 10,
) -> None:
    """Run full-text retrieval concurrently, then apply results to DB."""
    import asyncio

    total = len(papers)
    if total == 0:
        return

    sem = asyncio.Semaphore(concurrency)

    async def _fetch(paper: Paper) -> tuple[Paper, tuple[str, str] | None]:
        async with sem:
            result = await fetch_full_text_content(paper, settings)
        return paper, result

    # Fetch all full texts concurrently (HTTP only, no DB)
    log.info("fulltext_fetching", total=total, concurrency=concurrency)
    fetch_results = await asyncio.gather(*[_fetch(p) for p in papers])

    # Apply results sequentially (session-safe)
    retrieved = 0
    for i, (paper, result) in enumerate(fetch_results, 1):
        if result is not None:
            full_text, methods = result
            # Strip null bytes — PostgreSQL rejects \x00 in text columns
            paper.full_text_content = full_text.replace("\x00", "") if full_text else full_text
            paper.methods_section = methods.replace("\x00", "") if methods else methods
            paper.full_text_retrieved = True
            retrieved += 1
        else:
            paper.full_text_retrieved = False
        paper.pipeline_stage = PipelineStage.FULLTEXT_RETRIEVED

        if i % 50 == 0 or i == total:
            log.info("fulltext_progress", processed=i, total=total, retrieved=retrieved)

    await session.flush()
    log.info("fulltext_stage_complete", total=total, retrieved=retrieved)


async def _run_dedup(
    session: AsyncSession,
    papers: list[Paper],
    settings=None,
) -> tuple[list[Paper], int]:
    """Run dedup on new papers. Returns (non_duplicates, duplicate_count)."""
    dedup_kwargs = {}
    if settings is not None:
        dedup_kwargs = {
            "title_threshold": settings.dedup_title_threshold,
            "title_threshold_no_doi": settings.dedup_title_threshold_no_doi,
            "date_window_days": settings.dedup_date_window_days,
            "date_window_days_no_doi": settings.dedup_date_window_days_no_doi,
        }
    engine = DedupEngine(session, **dedup_kwargs)
    non_dups: list[Paper] = []
    dup_count = 0

    for paper in papers:
        record = {
            "doi": paper.doi,
            "title": paper.title,
            "authors": paper.authors,
            "posted_date": paper.posted_date,
        }
        result = await engine.check(record, paper_id=paper.id)
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
    concurrency: int = 10,
) -> list[Paper]:
    """Run enrichment on papers concurrently and store results."""
    import asyncio

    total = len(papers)
    if total == 0:
        return []

    sem = asyncio.Semaphore(concurrency)
    enriched: list[Paper] = []

    async def _enrich(paper: Paper) -> tuple[Paper, bool]:
        async with sem:
            try:
                result = await enrich_paper(paper, settings)
                return paper, result
            except Exception as exc:
                log.warning(
                    "enrichment_paper_error",
                    paper_id=str(paper.id),
                    error=_exc_str(exc),
                )
                return paper, None

    # Fetch all enrichment data concurrently (HTTP only, no DB writes)
    log.info("enrichment_fetching", total=total, concurrency=concurrency)
    fetch_results = await asyncio.gather(*[_enrich(p) for p in papers])

    # Apply results sequentially (session-safe)
    for paper, result in fetch_results:
        if result is not None:
            paper.enrichment_data = {
                **result.data,
                "_meta": {
                    "sources_succeeded": result.sources_succeeded,
                    "sources_failed": result.sources_failed,
                    "fetched_at": datetime.now(UTC).isoformat(),
                },
            }
            enriched.append(paper)

    await session.flush()
    log.info("enrichment_stage_complete", total=total, enriched=len(enriched))
    return enriched


async def _run_fulltext_translation(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    model: str,
    concurrency: int = 10,
) -> None:
    """Translate non-English methods sections to English after fulltext retrieval."""
    import asyncio

    total = len(papers)
    sem = asyncio.Semaphore(concurrency)
    translated = 0

    async def _translate(paper: Paper) -> None:
        nonlocal translated
        if not paper.methods_section:
            return

        prompt = (
            f"Translate the following scientific methods section from {paper.language} to English. "
            "Return ONLY the translated text, preserving all technical terminology, "
            "section headings, and formatting. Do not add any commentary.\n\n"
            f"{paper.methods_section}"
        )

        # Methods sections can be long — allow up to 8192 output tokens
        async with sem:
            result = await llm_client.call(
                model=model,
                system_prompt=(
                    "You are a scientific translator."
                    " Translate accurately, preserving"
                    " all technical detail."
                ),
                user_message=prompt,
                max_tokens=8192,
            )

        if result.error:
            log.warning("fulltext_translation_error", paper_id=str(paper.id), error=result.error)
            return

        raw = result.raw_response.strip()
        if raw:
            paper.original_methods_section = paper.methods_section
            paper.methods_section = raw
            translated += 1
            log.info("fulltext_translated", paper_id=str(paper.id), language=paper.language)

    await asyncio.gather(*[_translate(p) for p in papers])
    await session.flush()
    log.info("fulltext_translation_complete", total=total, translated=translated)


async def _run_translation(
    session: AsyncSession,
    llm_client: LLMClient,
    papers: list[Paper],
    model: str,
    concurrency: int = 10,
) -> None:
    """Translate non-English titles and abstracts to English using Haiku."""
    import asyncio
    import json

    total = len(papers)
    sem = asyncio.Semaphore(concurrency)
    translated = 0

    async def _translate(paper: Paper) -> None:
        nonlocal translated
        parts_to_translate = []
        if paper.title:
            parts_to_translate.append(f"Title: {paper.title}")
        if paper.abstract:
            parts_to_translate.append(f"Abstract: {paper.abstract}")

        if not parts_to_translate:
            return

        text = "\n\n".join(parts_to_translate)
        prompt = (
            f"Translate the following scientific paper metadata from {paper.language} to English. "
            "Return ONLY a JSON object with keys "
            '"title" and "abstract" '
            "(use null if not present). "
            "Preserve all technical and scientific terminology accurately.\n\n"
            f"{text}"
        )

        async with sem:
            result = await llm_client.call(
                model=model,
                system_prompt="You are a scientific translator. Respond with only valid JSON.",
                user_message=prompt,
            )

        if result.error:
            log.warning("translation_error", paper_id=str(paper.id), error=result.error)
            return

        try:
            raw = result.raw_response.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                raw = raw.rsplit("```", 1)[0]
            parsed = json.loads(raw)
            # Save originals
            paper.original_title = paper.title
            paper.original_abstract = paper.abstract
            # Replace with English
            if parsed.get("title"):
                paper.title = parsed["title"]
            if parsed.get("abstract"):
                paper.abstract = parsed["abstract"]
            translated += 1
        except (json.JSONDecodeError, KeyError) as exc:
            log.warning("translation_parse_error", paper_id=str(paper.id), error=str(exc))

    await asyncio.gather(*[_translate(p) for p in papers])
    await session.flush()
    log.info("translation_complete", total=total, translated=translated)
