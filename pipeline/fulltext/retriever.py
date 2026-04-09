"""Stage 3: Full-text retrieval cascade.

Tries multiple sources in priority order to fetch full-text content.
Extracts the methods section using the JATS or HTML parser.
Falls back gracefully if all sources fail — the paper still advances.
"""

from __future__ import annotations

import asyncio
import re

import httpx
import pymupdf
import structlog
from lxml import etree
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.fulltext.html_parser import extract_methods as html_extract
from pipeline.fulltext.jats_parser import extract_methods as jats_extract
from pipeline.fulltext.unpaywall import UnpaywallClient
from pipeline.models import Paper, PipelineStage, SourceServer

log = structlog.get_logger()

_PMC_ID_PATTERN = re.compile(r"(?:PMC)?(\d+)")


async def fetch_full_text_content(
    paper: Paper,
    settings,
) -> tuple[str, str] | None:
    """Run the full-text retrieval cascade for a single paper.

    Returns (full_text, methods_section) or None if no full text found.
    Pure HTTP — does not touch the database.
    """
    result = None

    is_preprint = paper.source_server in (SourceServer.BIORXIV, SourceServer.MEDRXIV)
    if paper.source_server == SourceServer.MEDRXIV:
        base_url = "https://www.medrxiv.org"
    else:
        base_url = "https://www.biorxiv.org"

    async with httpx.AsyncClient() as http:
        # Source 1: bioRxiv/medRxiv TDM XML
        if paper.doi and is_preprint:
            result = await _try_preprint_xml(
                http,
                base_url,
                paper.doi,
                settings.fulltext_request_delay,
            )

        # Source 1b: bioRxiv/medRxiv HTML fallback
        if result is None and paper.doi and is_preprint:
            result = await _try_preprint_html(
                http,
                base_url,
                paper.doi,
                settings.fulltext_request_delay,
            )

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

        # Source 4: Unpaywall (XML/HTML, then PDF fallback)
        if result is None and paper.doi and settings.unpaywall_email:
            result = await _try_unpaywall(http, paper.doi, settings)

        # Source 5: bioRxiv/medRxiv PDF as last resort
        if result is None and paper.doi and is_preprint:
            result = await _try_preprint_pdf(
                http,
                base_url,
                paper.doi,
                settings.fulltext_request_delay,
            )

    return result


async def retrieve_full_text(
    session: AsyncSession,
    paper: Paper,
    settings,
) -> None:
    """Run the full-text retrieval cascade for a single paper.

    Updates paper.full_text_content, paper.methods_section,
    paper.full_text_retrieved, and paper.pipeline_stage in-place.
    """
    result = await fetch_full_text_content(paper, settings)

    if result is not None:
        full_text, methods = result
        # Strip null bytes — PostgreSQL rejects \x00 in text columns
        full_text = full_text.replace("\x00", "") if full_text else full_text
        methods = methods.replace("\x00", "") if methods else methods

        # Quality gate: reject content that isn't usable article text
        if _is_usable_fulltext(full_text, paper.abstract or ""):
            paper.full_text_content = full_text
            paper.methods_section = methods
            paper.full_text_retrieved = True
            log.info("fulltext_retrieved", paper_id=str(paper.id))
        else:
            paper.full_text_content = None
            paper.methods_section = None
            paper.full_text_retrieved = False
            log.info(
                "fulltext_rejected_quality",
                paper_id=str(paper.id),
                content_len=len(full_text or ""),
            )
    else:
        paper.full_text_retrieved = False
        log.info("fulltext_not_found", paper_id=str(paper.id))

    paper.pipeline_stage = PipelineStage.FULLTEXT_RETRIEVED
    await session.flush()


def _is_usable_fulltext(content: str | None, abstract: str) -> bool:
    """Check if retrieved content is usable article text.

    Rejects empty content, raw PDF bytes, and content that is barely
    longer than the abstract (likely a landing page or paywall stub).
    """
    if not content or not content.strip():
        return False

    # Raw PDF bytes that weren't extracted
    if content.lstrip().startswith("%PDF"):
        return False

    # Absolute minimum: at least 1000 chars for a research article
    if len(content) < 1000:
        return False

    # If we have a substantial abstract, content should be meaningfully longer
    abstract_len = len(abstract)
    if abstract_len > 500 and len(content) < abstract_len * 2:
        return False

    return True


def _extract_pmc_id(url: str) -> str | None:
    """Extract PMC ID from a URL like /pmc/articles/PMC7654321/ or /pmc/articles/7654321/."""
    match = _PMC_ID_PATTERN.search(url)
    if not match:
        return None
    digits = match.group(1)
    return f"PMC{digits}"


async def _try_preprint_xml(
    http: httpx.AsyncClient,
    base_url: str,
    doi: str,
    delay: float,
) -> tuple[str, str] | None:
    """Source 1: bioRxiv/medRxiv TDM XML."""
    url = f"{base_url}/content/{doi}.full.xml"
    try:
        await asyncio.sleep(delay)
        resp = await http.get(url, timeout=30.0, follow_redirects=True)
        if resp.status_code == 200:
            # Check if response is actually HTML (bioRxiv XML endpoints broken as of 2026)
            content_type = resp.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                log.debug("preprint_xml_returns_html", doi=doi, url=url)
                return None
            return jats_extract(resp.content)
    except (httpx.HTTPError, etree.Error, ValueError) as exc:
        log.debug("preprint_xml_error", doi=doi, error=str(exc))
    return None


async def _try_preprint_html(
    http: httpx.AsyncClient,
    base_url: str,
    doi: str,
    delay: float,
) -> tuple[str, str] | None:
    """Source 1b: bioRxiv/medRxiv HTML full text."""
    url = f"{base_url}/content/{doi}.full"
    try:
        await asyncio.sleep(delay)
        resp = await http.get(url, timeout=30.0, follow_redirects=True)
        if resp.status_code == 200 and resp.content:
            return html_extract(resp.content)
    except (httpx.HTTPError, ValueError) as exc:
        log.debug("preprint_html_error", doi=doi, error=str(exc))
    return None


async def _try_preprint_pdf(
    http: httpx.AsyncClient,
    base_url: str,
    doi: str,
    delay: float,
) -> tuple[str, str] | None:
    """Source 5: bioRxiv/medRxiv PDF as last resort."""
    url = f"{base_url}/content/{doi}.full.pdf"
    try:
        await asyncio.sleep(delay)
        resp = await http.get(url, timeout=60.0, follow_redirects=True)
        if resp.status_code == 200 and resp.content:
            return _extract_from_pdf(resp.content, doi)
    except (httpx.HTTPError, ValueError) as exc:
        log.debug("preprint_pdf_error", doi=doi, error=str(exc))
    return None


async def _try_europepmc(http: httpx.AsyncClient, doi: str, delay: float) -> tuple[str, str] | None:
    """Source 2: Europe PMC full text XML."""
    # First, find the Europe PMC source/id for this DOI
    search_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": f"DOI:{doi}", "format": "json", "resultType": "core", "pageSize": 1}
    try:
        await asyncio.sleep(delay)
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
        await asyncio.sleep(delay)
        resp = await http.get(ft_url, timeout=30.0)
        if resp.status_code == 200 and resp.content:
            return jats_extract(resp.content)
    except (httpx.HTTPError, etree.Error, ValueError) as exc:
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
        await asyncio.sleep(delay)
        resp = await http.get(url, params=params, timeout=30.0)
        if resp.status_code == 200 and resp.content:
            return jats_extract(resp.content)
    except (httpx.HTTPError, etree.Error, ValueError) as exc:
        log.debug("pmc_fulltext_error", pmc_id=pmc_id, error=str(exc))
    return None


async def _try_unpaywall(http: httpx.AsyncClient, doi: str, settings) -> tuple[str, str] | None:
    """Source 4: Unpaywall → fetch OA URL → parse (XML, HTML, or PDF)."""
    try:
        async with UnpaywallClient(
            email=settings.unpaywall_email,
            request_delay=settings.unpaywall_request_delay,
        ) as uw:
            result = await uw.lookup(doi)

        if result is None:
            return None

        timeout = 60.0 if result.content_type == "pdf" else 30.0
        resp = await http.get(result.url, timeout=timeout, follow_redirects=True)
        if resp.status_code != 200:
            return None

        if result.content_type == "xml":
            return jats_extract(resp.content)
        if result.content_type == "pdf":
            return _extract_from_pdf(resp.content, doi)
        return html_extract(resp.content)

    except (httpx.HTTPError, etree.Error, ValueError) as exc:
        log.debug("unpaywall_fulltext_error", doi=doi, error=str(exc))
    return None


def _extract_from_pdf(pdf_bytes: bytes, doi: str) -> tuple[str, str] | None:
    """Extract text from PDF bytes and identify the methods section."""
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text() for page in doc]
        doc.close()

        full_text = "\n".join(pages)
        if not full_text.strip():
            log.debug("pdf_no_text", doi=doi)
            return None

        methods = _find_methods_in_text(full_text)
        return (full_text, methods)
    except Exception as exc:
        log.warning("pdf_extract_error", doi=doi, error=str(exc), exc_type=type(exc).__name__)
        return None


_METHODS_HEADING_RE = re.compile(
    r"^(?:[\dIVXivx]+\.?\s+)?"
    r"(materials?\s*(?:and|&)\s*methods"
    r"|methods?\s*(?:details|summary|section)?"
    r"|experimental\s*(?:procedures|methods|model\s*details|design)"
    r"|study\s*methods"
    r"|star\s*methods"
    r"|online\s*methods"
    r"|supplementa(?:l|ry)\s*experimental\s*procedures"
    r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_SECTION_HEADING_RE = re.compile(
    r"^(results|discussion|acknowledgements?|references|conclusions?|data\s*(?:and\s*code\s*)?availability|supplementary|funding|author\s*contributions?|declaration\s*of\s*interests?|resource\s*availability|supporting\s*information)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _find_methods_in_text(text: str) -> str:
    """Find the methods section in plain text by heading patterns."""
    # Try numbered methods section first (most common)
    match = _METHODS_HEADING_RE.search(text)
    if match:
        start = match.start()
        end_match = _SECTION_HEADING_RE.search(text, match.end())
        end = end_match.start() if end_match else len(text)
        methods = text[start:end].strip()
        if methods and len(methods) < len(text) * 0.9:  # Sanity check
            return methods

    # Try unnumbered "Methods" section
    plain_methods_re = re.compile(
        r'\n\s*(materials?\s*(?:and|&)\s*methods|methods|experimental\s*(?:procedures|methods))\s*\n',
        re.IGNORECASE | re.MULTILINE,
    )
    match = plain_methods_re.search(text)
    if match:
        start = match.start()
        # Look for next major section
        next_section_re = re.compile(
            r'\n\s*(?:results|discussion|conclusion|acknowledgements?|references|data\s*availability|author\s*contributions?)\s*\n',
            re.IGNORECASE | re.MULTILINE,
        )
        end_match = next_section_re.search(text, match.end())
        end = end_match.start() if end_match else len(text)
        methods = text[start:end].strip()
        if methods and 200 < len(methods) < len(text) * 0.8:
            return methods

    return text
