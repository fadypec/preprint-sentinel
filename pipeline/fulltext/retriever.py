"""Stage 3: Full-text retrieval cascade.

Tries multiple sources in priority order to fetch full-text content.
Extracts the methods section using the JATS or HTML parser.
Falls back gracefully if all sources fail — the paper still advances.
"""

from __future__ import annotations

import re

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.fulltext.html_parser import extract_methods as html_extract
from pipeline.fulltext.jats_parser import extract_methods as jats_extract
from pipeline.fulltext.unpaywall import UnpaywallClient
from pipeline.models import Paper, PipelineStage, SourceServer

log = structlog.get_logger()

_PMC_ID_PATTERN = re.compile(r"PMC\d+")


async def retrieve_full_text(
    session: AsyncSession,
    paper: Paper,
    settings,
) -> None:
    """Run the full-text retrieval cascade for a single paper.

    Updates paper.full_text_content, paper.methods_section,
    paper.full_text_retrieved, and paper.pipeline_stage in-place.
    """
    result = None

    async with httpx.AsyncClient() as http:
        # Source 1: bioRxiv/medRxiv TDM XML
        if paper.doi and paper.source_server in (SourceServer.BIORXIV, SourceServer.MEDRXIV):
            result = await _try_biorxiv(http, paper.doi, settings.fulltext_request_delay)

        # Source 2: Europe PMC full text
        if result is None and paper.doi:
            result = await _try_europepmc(http, paper.doi, settings.fulltext_request_delay)

        # Source 3: PubMed Central OA
        if result is None and paper.full_text_url:
            pmc_id = _extract_pmc_id(paper.full_text_url)
            if pmc_id:
                result = await _try_pmc(
                    http, pmc_id, settings.fulltext_request_delay, settings.ncbi_api_key
                )

        # Source 4: Unpaywall
        if result is None and paper.doi and settings.unpaywall_email:
            result = await _try_unpaywall(http, paper.doi, settings)

    if result is not None:
        full_text, methods = result
        paper.full_text_content = full_text
        paper.methods_section = methods
        paper.full_text_retrieved = True
        log.info("fulltext_retrieved", paper_id=str(paper.id))
    else:
        paper.full_text_retrieved = False
        log.info("fulltext_not_found", paper_id=str(paper.id))

    paper.pipeline_stage = PipelineStage.FULLTEXT_RETRIEVED
    await session.flush()


def _extract_pmc_id(url: str) -> str | None:
    """Extract PMC ID from a URL like https://...pmc/articles/PMC7654321/."""
    match = _PMC_ID_PATTERN.search(url)
    return match.group(0) if match else None


async def _try_biorxiv(http: httpx.AsyncClient, doi: str, delay: float) -> tuple[str, str] | None:
    """Source 1: bioRxiv/medRxiv TDM XML."""
    url = f"https://www.biorxiv.org/content/{doi}.full.xml"
    try:
        resp = await http.get(url, timeout=30.0)
        if resp.status_code == 200:
            return jats_extract(resp.content)
    except (httpx.HTTPError, Exception) as exc:
        log.debug("biorxiv_fulltext_error", doi=doi, error=str(exc))
    return None


async def _try_europepmc(http: httpx.AsyncClient, doi: str, delay: float) -> tuple[str, str] | None:
    """Source 2: Europe PMC full text XML."""
    # First, find the Europe PMC source/id for this DOI
    search_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": f"DOI:{doi}", "format": "json", "resultType": "core", "pageSize": 1}
    try:
        resp = await http.get(search_url, params=params, timeout=30.0)
        if resp.status_code != 200:
            return None
        results = resp.json().get("resultList", {}).get("result", [])
        if not results:
            return None
        source = results[0].get("source", "")
        record_id = results[0].get("id", "")
        if not source or not record_id:
            return None

        # Fetch full text
        ft_url = (
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/{source}/{record_id}/fullTextXML"
        )
        resp = await http.get(ft_url, timeout=30.0)
        if resp.status_code == 200 and resp.content:
            return jats_extract(resp.content)
    except (httpx.HTTPError, Exception) as exc:
        log.debug("europepmc_fulltext_error", doi=doi, error=str(exc))
    return None


async def _try_pmc(
    http: httpx.AsyncClient, pmc_id: str, delay: float, api_key: str
) -> tuple[str, str] | None:
    """Source 3: PubMed Central OA via efetch."""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params: dict = {"db": "pmc", "id": pmc_id, "rettype": "xml"}
    if api_key:
        params["api_key"] = api_key
    try:
        resp = await http.get(url, params=params, timeout=30.0)
        if resp.status_code == 200 and resp.content:
            return jats_extract(resp.content)
    except (httpx.HTTPError, Exception) as exc:
        log.debug("pmc_fulltext_error", pmc_id=pmc_id, error=str(exc))
    return None


async def _try_unpaywall(http: httpx.AsyncClient, doi: str, settings) -> tuple[str, str] | None:
    """Source 4: Unpaywall → fetch OA URL → parse."""
    try:
        async with UnpaywallClient(
            email=settings.unpaywall_email,
            request_delay=settings.unpaywall_request_delay,
        ) as uw:
            result = await uw.lookup(doi)

        if result is None:
            return None

        if result.content_type == "pdf":
            log.debug("unpaywall_pdf_skipped", doi=doi)
            return None

        resp = await http.get(result.url, timeout=30.0)
        if resp.status_code != 200:
            return None

        if result.content_type == "xml":
            return jats_extract(resp.content)
        return html_extract(resp.content)

    except (httpx.HTTPError, Exception) as exc:
        log.debug("unpaywall_fulltext_error", doi=doi, error=str(exc))
    return None
