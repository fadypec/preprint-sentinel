"""Enrichment orchestrator -- merges data from OpenAlex, Semantic Scholar, ORCID, and Crossref.

Usage:
    result = await enrich_paper(paper, settings)
    paper.enrichment_data = {**result.data, "_meta": {...}}
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from pipeline.enrichment.crossref import CrossrefEnrichmentClient
from pipeline.enrichment.openalex import OpenAlexClient
from pipeline.enrichment.orcid import OrcidClient
from pipeline.enrichment.semantic_scholar import SemanticScholarClient
from pipeline.models import Paper

log = structlog.get_logger()


@dataclass(frozen=True)
class EnrichmentResult:
    """Result of enriching a single paper from all sources."""

    data: dict
    sources_succeeded: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    partial: bool = False


async def enrich_paper(paper: Paper, settings) -> EnrichmentResult:
    """Fetch enrichment data from all configured sources.

    Each source is wrapped in try/except -- individual failures are recorded
    but do not prevent other sources from being queried.
    """
    doi = paper.doi or ""
    corresponding_author = paper.corresponding_author or ""

    merged_data: dict = {}
    sources_succeeded: list[str] = []
    sources_failed: list[str] = []

    # Known ORCID from OpenAlex (populated below if available)
    known_orcid: str | None = None

    # 1. OpenAlex
    try:
        async with OpenAlexClient(
            email=settings.openalex_email,
            request_delay=settings.openalex_request_delay,
        ) as oa_client:
            oa_data = await oa_client.lookup(doi)
        if oa_data is not None:
            merged_data["openalex"] = oa_data
            sources_succeeded.append("openalex")
            # Extract ORCID for first/corresponding author
            known_orcid = _extract_orcid_from_openalex(oa_data, corresponding_author)
        else:
            # DOI not found is not an error, but no data to merge
            sources_succeeded.append("openalex")
    except Exception:
        log.warning("enrichment_openalex_failed", paper_id=str(paper.id), exc_info=True)
        sources_failed.append("openalex")

    # 2. Semantic Scholar
    try:
        s2_api_key = settings.semantic_scholar_api_key.get_secret_value()
        async with SemanticScholarClient(
            api_key=s2_api_key,
            request_delay=settings.semantic_scholar_request_delay,
        ) as s2_client:
            s2_data = await s2_client.lookup(doi)
        if s2_data is not None:
            merged_data["s2"] = s2_data
        sources_succeeded.append("semantic_scholar")
    except Exception:
        log.warning("enrichment_s2_failed", paper_id=str(paper.id), exc_info=True)
        sources_failed.append("semantic_scholar")

    # 3. ORCID (for corresponding/first author only)
    try:
        author_name = corresponding_author
        if not author_name:
            # Fall back to first author
            authors = paper.authors or []
            if authors and isinstance(authors, list) and len(authors) > 0:
                author_name = authors[0].get("name", "")

        if author_name:
            async with OrcidClient(
                request_delay=settings.orcid_request_delay,
            ) as orcid_client:
                orcid_data = await orcid_client.lookup(author_name, known_orcid=known_orcid)
            if orcid_data is not None:
                merged_data["orcid"] = orcid_data
        sources_succeeded.append("orcid")
    except Exception:
        log.warning("enrichment_orcid_failed", paper_id=str(paper.id), exc_info=True)
        sources_failed.append("orcid")

    # 4. Crossref funder info (supplements OpenAlex funder data)
    try:
        crossref_email = getattr(settings, "crossref_email", "") or settings.openalex_email
        async with CrossrefEnrichmentClient(
            email=crossref_email,
            request_delay=getattr(settings, "crossref_request_delay", 1.0),
        ) as cr_client:
            cr_data = await cr_client.lookup(doi)
        if cr_data is not None:
            merged_data["crossref"] = cr_data
        sources_succeeded.append("crossref")
    except Exception:
        log.warning("enrichment_crossref_failed", paper_id=str(paper.id), exc_info=True)
        sources_failed.append("crossref")

    partial = len(sources_failed) > 0

    log.info(
        "enrichment_complete",
        paper_id=str(paper.id),
        succeeded=sources_succeeded,
        failed=sources_failed,
        partial=partial,
    )

    return EnrichmentResult(
        data=merged_data,
        sources_succeeded=sources_succeeded,
        sources_failed=sources_failed,
        partial=partial,
    )


def _extract_orcid_from_openalex(oa_data: dict, corresponding_author: str) -> str | None:
    """Try to find the ORCID for the corresponding (or first) author from OpenAlex data."""
    authors = oa_data.get("authors", [])
    if not authors:
        return None

    # Try to match corresponding author by name
    if corresponding_author:
        corresponding_lower = corresponding_author.lower()
        for author in authors:
            if (
                author.get("name", "").lower() in corresponding_lower
                or corresponding_lower in author.get("name", "").lower()
            ):
                if author.get("orcid"):
                    return author["orcid"]

    # Fall back to first author's ORCID
    if authors:
        first_author = authors[0]
        return first_author.get("orcid")
    return None
