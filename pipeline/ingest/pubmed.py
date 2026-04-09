"""Async client for PubMed E-utilities (esearch + efetch).

Usage:
    async with PubmedClient(api_key="...", query_mode="all") as client:
        async for paper in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30)):
            print(paper["title"])
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date

import httpx
import structlog
from lxml import etree

from pipeline.http_retry import request_with_retry
from pipeline.models import SourceServer

log = structlog.get_logger()

DEFAULT_MESH_QUERY = (
    '(virology[MeSH] OR microbiology[MeSH] OR "synthetic biology"[MeSH] OR '
    '"genetic engineering"[MeSH] OR "gain of function"[tiab] OR '
    '"gain-of-function"[tiab] OR "directed evolution"[tiab] OR '
    '"reverse genetics"[tiab] OR "gene drive"[tiab] OR "gene drives"[tiab] OR '
    '"select agent"[tiab] OR "select agents"[tiab] OR '
    '"dual use"[tiab] OR "dual-use"[tiab] OR '
    '"pathogen enhancement"[tiab] OR "immune evasion"[tiab] OR '
    '"host range"[tiab] OR "transmissibility"[tiab] OR '
    '"virulence factor"[tiab] OR "virulence factors"[tiab] OR '
    'toxins[MeSH] OR "biological warfare"[MeSH] OR "biodefense"[MeSH] OR '
    'CRISPR[tiab] OR "base editing"[tiab] OR '
    '"pandemic preparedness"[tiab] OR "pandemic pathogen"[tiab] OR '
    '"biosafety level"[tiab] OR "BSL-3"[tiab] OR "BSL-4"[tiab] OR '
    'prions[MeSH] OR "mirror life"[tiab] OR "xenobiology"[tiab] OR '
    '"de novo protein design"[tiab] OR "protein design"[tiab] OR '
    '"aerosol transmission"[tiab] OR "airborne transmission"[tiab])'
)


class PubmedClient:
    """Async client for PubMed via NCBI E-utilities."""

    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    FETCH_BATCH_SIZE = 200

    def __init__(
        self,
        api_key: str = "",
        request_delay: float = 0.1,
        max_retries: int = 3,
        query_mode: str = "all",
        mesh_query: str = DEFAULT_MESH_QUERY,
    ) -> None:
        if query_mode not in ("all", "mesh_filtered"):
            msg = f"Invalid query_mode: {query_mode!r} (expected 'all' or 'mesh_filtered')"
            raise ValueError(msg)
        self.api_key = api_key
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.query_mode = query_mode
        self.mesh_query = mesh_query
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> PubmedClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # -- Public API ----------------------------------------------------------

    async def fetch_papers(self, from_date: date, to_date: date) -> AsyncGenerator[dict, None]:
        """Search PubMed and yield normalised paper dicts."""
        webenv, query_key, count = await self._search(from_date, to_date)
        if count == 0:
            return

        log.info("pubmed_search_complete", count=count, query_mode=self.query_mode)

        for retstart in range(0, count, self.FETCH_BATCH_SIZE):
            articles = await self._fetch_batch(webenv, query_key, retstart)
            for article in articles:
                yield article

            if retstart + self.FETCH_BATCH_SIZE < count:
                log.info(
                    "pubmed_batch_fetched",
                    retstart=retstart,
                    batch_size=len(articles),
                    total=count,
                )

    # -- HTTP helpers --------------------------------------------------------

    async def _search(self, from_date: date, to_date: date) -> tuple[str, str, int]:
        """Run esearch and return (webenv, query_key, count)."""
        params: dict = {
            "db": "pubmed",
            "retmode": "json",
            "retmax": 0,
            "usehistory": "y",
            "datetype": "pdat",
            "mindate": from_date.strftime("%Y/%m/%d"),
            "maxdate": to_date.strftime("%Y/%m/%d"),
        }
        if self.query_mode == "mesh_filtered":
            params["term"] = self.mesh_query
        if self.api_key:
            params["api_key"] = self.api_key

        resp = await self._request(self.ESEARCH_URL, params)
        data = resp.json()
        result = data.get("esearchresult", {})
        return (
            result.get("webenv", ""),
            result.get("querykey", ""),
            int(result.get("count", 0)),
        )

    async def _fetch_batch(self, webenv: str, query_key: str, retstart: int) -> list[dict]:
        """Fetch a batch of articles via efetch and parse XML."""
        params: dict = {
            "db": "pubmed",
            "rettype": "xml",
            "retmode": "xml",
            "retmax": self.FETCH_BATCH_SIZE,
            "retstart": retstart,
            "webenv": webenv,
            "query_key": query_key,
        }
        if self.api_key:
            params["api_key"] = self.api_key

        resp = await self._request(self.EFETCH_URL, params)
        return self._parse_articles(resp.content)

    async def _request(self, url: str, params: dict) -> httpx.Response:
        """Make a GET request with retry and exponential backoff."""
        if self._client is None:
            raise RuntimeError("Use PubmedClient as async context manager")

        resp = await request_with_retry(
            self._client,
            url,
            params=params,
            timeout=60.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            retry_on=(httpx.TimeoutException, httpx.RemoteProtocolError),
            source="pubmed",
        )
        assert resp is not None  # none_on_404 not set, so always Response or raise
        return resp

    # -- XML parsing ---------------------------------------------------------

    def _parse_articles(self, xml_bytes: bytes) -> list[dict]:
        """Parse PubmedArticleSet XML into normalised dicts."""
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(xml_bytes, parser=parser)
        articles = []
        for elem in root.findall(".//PubmedArticle"):
            try:
                articles.append(self._normalise_article(elem))
            except Exception:
                log.exception("pubmed_parse_error")
                continue
        return articles

    def _normalise_article(self, elem) -> dict:
        """Extract fields from a single PubmedArticle element."""
        citation = elem.find("MedlineCitation")
        if citation is None:
            raise ValueError("PubmedArticle missing MedlineCitation element")
        article = citation.find("Article")
        if article is None:
            raise ValueError("MedlineCitation missing Article element")

        # Title — prefer ArticleTitle, fall back to VernacularTitle for non-English
        title_elem = article.find("ArticleTitle")
        title = "".join(title_elem.itertext()).strip() if title_elem is not None else ""

        vernacular_title = None
        vt_elem = article.find("VernacularTitle")
        if vt_elem is not None:
            vernacular_title = "".join(vt_elem.itertext()).strip()

        if not title or title == "[Not Available].":
            title = vernacular_title or title

        # Language
        lang_elem = article.find("Language")
        language = lang_elem.text if lang_elem is not None else "eng"

        # Authors
        authors = []
        for author in article.findall(".//Author"):
            last = author.findtext("LastName", "")
            fore = author.findtext("ForeName", "")
            if last:
                initial = f"{fore[0]}." if fore else ""
                name = f"{last}, {initial}" if initial else last
                authors.append({"name": name})

        # Corresponding institution (first author's affiliation)
        first_affil = article.findtext(".//Author[1]/AffiliationInfo/Affiliation")

        # Abstract (may be structured with labels)
        abstract_parts = []
        for abs_text in article.findall(".//AbstractText"):
            label = abs_text.get("Label")
            text = "".join(abs_text.itertext()).strip()
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = " ".join(abstract_parts)

        # Article IDs — DOI and PMC from PubmedData
        doi = None
        pmc_id = None
        pubmed_data = elem.find("PubmedData")
        if pubmed_data is not None:
            for aid in pubmed_data.findall(".//ArticleId"):
                id_type = aid.get("IdType")
                if id_type == "doi" and doi is None:
                    doi = aid.text
                elif id_type == "pmc" and pmc_id is None:
                    pmc_id = aid.text

        # Publication date
        posted_date = self._extract_date(elem)

        # MeSH terms
        mesh_terms = [
            desc.text for desc in citation.findall(".//MeshHeading/DescriptorName") if desc.text
        ]
        subject_category = "; ".join(mesh_terms) if mesh_terms else None

        # Full text URL from PMC
        full_text_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/" if pmc_id else None

        return {
            "doi": doi,
            "title": title,
            "authors": authors,
            "corresponding_author": None,
            "corresponding_institution": first_affil,
            "abstract": abstract,
            "source_server": SourceServer.PUBMED,
            "posted_date": posted_date,
            "subject_category": subject_category,
            "version": 1,
            "full_text_url": full_text_url,
            "_language": language,
            "_vernacular_title": vernacular_title,
        }

    def _extract_date(self, elem) -> date:
        """Extract publication date from PubmedArticle."""
        for pub_date in elem.findall(".//PubmedData/History/PubMedPubDate"):
            if pub_date.get("PubStatus") == "pubmed":
                year = int(pub_date.findtext("Year", "0"))
                month = int(pub_date.findtext("Month", "1"))
                day = int(pub_date.findtext("Day", "1"))
                return date(year, month, day)
        log.warning("pubmed_date_fallback", msg="No PubMedPubDate with PubStatus=pubmed found")
        return date.today()
