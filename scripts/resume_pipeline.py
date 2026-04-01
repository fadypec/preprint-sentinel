"""Resume pipeline from a given stage, skipping already-completed stages.

Usage:
    python -m scripts.resume_pipeline                    # auto-detect from DB
    python -m scripts.resume_pipeline --from fulltext    # start from fulltext retrieval
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import func, select

from pipeline.config import get_settings
from pipeline.db import make_engine, make_session_factory
from pipeline.enrichment.enricher import enrich_paper
from pipeline.fulltext.retriever import fetch_full_text_content
from pipeline.models import Paper, PipelineStage
from pipeline.orchestrator import _run_fulltext_translation
from pipeline.triage.adjudication import run_adjudication
from pipeline.triage.llm import LLMClient
from pipeline.triage.methods_analysis import run_methods_analysis

log = structlog.get_logger()

STAGES = ["fulltext", "methods", "enrichment", "adjudication"]


async def resume(start_from: str | None = None) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url.get_secret_value())
    session_factory = make_session_factory(engine)
    llm_client = LLMClient(api_key=settings.anthropic_api_key.get_secret_value())

    from_date = date.today() - timedelta(days=2)

    # Auto-detect: find the earliest stage that has papers to process
    if start_from is None:
        async with session_factory() as session:
            for stage_name, pipeline_stage in [
                ("fulltext", PipelineStage.COARSE_FILTERED),
                ("methods", PipelineStage.FULLTEXT_RETRIEVED),
                ("enrichment", PipelineStage.METHODS_ANALYSED),
                ("adjudication", PipelineStage.METHODS_ANALYSED),
            ]:
                stmt = (
                    select(func.count())
                    .select_from(Paper)
                    .where(
                        Paper.pipeline_stage == pipeline_stage,
                        Paper.posted_date >= from_date,
                    )
                )
                result = await session.execute(stmt)
                count = result.scalar()
                if count and count > 0:
                    start_from = stage_name
                    log.info("auto_detected_stage", stage=stage_name, papers=count)
                    break

    if start_from is None:
        log.info("nothing_to_resume")
        return

    stage_idx = STAGES.index(start_from)
    stages_to_run = STAGES[stage_idx:]
    log.info("resuming_pipeline", stages=stages_to_run)

    if "fulltext" in stages_to_run:
        async with session_factory() as session:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.COARSE_FILTERED,
                Paper.coarse_filter_passed.is_(True),
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            papers = list(result.scalars().all())

            total = len(papers)
            log.info("stage_starting", stage="fulltext_retrieval", papers_to_process=total)

            if total > 0:
                sem = asyncio.Semaphore(10)

                async def _fetch(paper: Paper) -> tuple[Paper, tuple[str, str] | None]:
                    async with sem:
                        r = await fetch_full_text_content(paper, settings)
                    return paper, r

                fetch_results = await asyncio.gather(*[_fetch(p) for p in papers])

                retrieved = 0
                for i, (paper, ft_result) in enumerate(fetch_results, 1):
                    if ft_result is not None:
                        full_text, methods = ft_result
                        paper.full_text_content = full_text
                        paper.methods_section = methods
                        paper.full_text_retrieved = True
                        retrieved += 1
                    else:
                        paper.full_text_retrieved = False
                    paper.pipeline_stage = PipelineStage.FULLTEXT_RETRIEVED

                    if i % 50 == 0 or i == total:
                        log.info("fulltext_progress", processed=i, total=total, retrieved=retrieved)

                await session.flush()
                await session.commit()
                log.info(
                    "stage_complete",
                    stage="fulltext_retrieval",
                    total=total,
                    retrieved=retrieved,
                )

    # Fulltext translation for non-English papers (runs after fulltext, before methods)
    if "fulltext" in stages_to_run or "methods" in stages_to_run:
        async with session_factory() as session:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.FULLTEXT_RETRIEVED,
                Paper.posted_date >= from_date,
                Paper.full_text_retrieved.is_(True),
                Paper.language.isnot(None),
                Paper.language != "eng",
                Paper.original_methods_section.is_(None),  # not already translated
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
                log.info("stage_complete", stage="fulltext_translation", total=len(non_english_ft))

    if "methods" in stages_to_run:
        async with session_factory() as session:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.FULLTEXT_RETRIEVED,
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            papers = list(result.scalars().all())

            log.info("stage_starting", stage="methods_analysis", papers_to_process=len(papers))
            if papers:
                await run_methods_analysis(
                    session=session,
                    llm_client=llm_client,
                    papers=papers,
                    use_batch=settings.use_batch_api,
                    model=settings.stage2_model,
                )
                await session.commit()
                log.info("stage_complete", stage="methods_analysis", total=len(papers))

    if "enrichment" in stages_to_run:
        async with session_factory() as session:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.METHODS_ANALYSED,
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            papers = list(result.scalars().all())

            log.info("stage_starting", stage="enrichment", papers_to_process=len(papers))
            if papers:
                enriched = 0
                total = len(papers)
                for i, paper in enumerate(papers, 1):
                    try:
                        enrich_result = await enrich_paper(paper, settings)
                        paper.enrichment_data = {
                            **enrich_result.data,
                            "_meta": {
                                "sources_succeeded": enrich_result.sources_succeeded,
                                "sources_failed": enrich_result.sources_failed,
                                "fetched_at": datetime.now(UTC).isoformat(),
                            },
                        }
                        enriched += 1
                    except Exception as exc:
                        log.warning(
                            "enrichment_paper_error",
                            paper_id=str(paper.id),
                            error=str(exc),
                        )

                    if i % 10 == 0 or i == total:
                        log.info("enrichment_progress", processed=i, total=total, enriched=enriched)

                await session.flush()
                await session.commit()
                log.info("stage_complete", stage="enrichment", total=total, enriched=enriched)

    if "adjudication" in stages_to_run:
        async with session_factory() as session:
            stmt = select(Paper).where(
                Paper.pipeline_stage == PipelineStage.METHODS_ANALYSED,
                Paper.posted_date >= from_date,
            )
            result = await session.execute(stmt)
            papers = list(result.scalars().all())

            log.info("stage_starting", stage="adjudication", papers_to_process=len(papers))
            if papers:
                await run_adjudication(
                    session=session,
                    llm_client=llm_client,
                    papers=papers,
                    model=settings.stage3_model,
                    min_tier=settings.adjudication_min_tier,
                )
                await session.commit()
                log.info("stage_complete", stage="adjudication", total=len(papers))

    log.info("resume_complete")
    await engine.dispose()


if __name__ == "__main__":
    start = None
    if "--from" in sys.argv:
        idx = sys.argv.index("--from")
        start = sys.argv[idx + 1]
    asyncio.run(resume(start))
