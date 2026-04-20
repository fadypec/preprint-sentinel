"""Async client for the Crossref API — harvests preprints by DOI prefix.

Covers Research Square (10.21203), ChemRxiv (10.26434), SSRN (10.2139).

Usage:
    async with CrossrefClient(email="you@example.com") as client:
        async for paper in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30)):
            print(paper["title"])
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from datetime import date

import httpx
import structlog

from pipeline.http_retry import request_with_retry
from pipeline.models import SourceServer

log = structlog.get_logger()

# SSRN uses from-created-date instead of from-posted-date (which returns 0).
_DEFAULT_SOURCES: dict[str, str] = {
    "research_square": "10.21203",
    "chemrxiv": "10.26434",
    "ssrn": "10.2139",
}

# Prefixes that need from-created-date instead of from-posted-date
_CREATED_DATE_PREFIXES: set[str] = {"10.2139"}

_SOURCE_SERVER_MAP: dict[str, SourceServer] = {
    "research_square": SourceServer.RESEARCH_SQUARE,
    "chemrxiv": SourceServer.CHEMRXIV,
    "ssrn": SourceServer.SSRN,
}

# Regex to strip HTML/JATS tags from abstracts
_TAG_RE = re.compile(r"<[^>]+>")


class CrossrefClient:
    """Async client for Crossref preprint harvest by DOI prefix."""

    BASE_URL = "https://api.crossref.org/works"
    PAGE_SIZE = 100

    def __init__(
        self,
        email: str = "",
        request_delay: float = 1.0,
        max_retries: int = 3,
        sources: dict[str, str] | None = None,
        max_pages_per_source: int = 10,
    ) -> None:
        self.email = email
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.sources = sources if sources is not None else _DEFAULT_SOURCES
        self.max_pages_per_source = max_pages_per_source
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> CrossrefClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # -- Public API ----------------------------------------------------------

    async def fetch_papers(self, from_date: date, to_date: date) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts from all configured Crossref sources."""
        for source_name, prefix in self.sources.items():
            try:
                async for paper in self._fetch_source(source_name, prefix, from_date, to_date):
                    yield paper
            except Exception as exc:
                # Log and skip this prefix — don't let one failing source
                # (e.g., Research Square 400) kill ChemRxiv and SSRN
                log.warning(
                    "crossref_prefix_error",
                    source=source_name,
                    prefix=prefix,
                    error=f"{type(exc).__name__}: {exc}",
                )

    # -- Internal ------------------------------------------------------------

    async def _fetch_source(
        self,
        source_name: str,
        prefix: str,
        from_date: date,
        to_date: date,
    ) -> AsyncGenerator[dict, None]:
        """Paginate through results for a single DOI prefix."""
        cursor = "*"
        total_fetched = 0
        pages_fetched = 0
        while True:
            data = await self._fetch_page(prefix, from_date, to_date, cursor)
            items = data.get("message", {}).get("items", [])
            if not items:
                break

            for item in items:
                yield self._normalise(item, source_name)
            total_fetched += len(items)
            pages_fetched += 1

            next_cursor = data.get("message", {}).get("next-cursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

            total_results = data.get("message", {}).get("total-results", 0)
            log.info(
                "page_fetched",
                source=f"crossref:{source_name}",
                fetched_so_far=total_fetched,
                total=total_results,
            )

            if pages_fetched >= self.max_pages_per_source:
                log.info(
                    "crossref_page_limit_reached",
                    source=source_name,
                    pages=pages_fetched,
                    fetched=total_fetched,
                    total=total_results,
                )
                break

    async def _fetch_page(
        self,
        prefix: str,
        from_date: date,
        to_date: date,
        cursor: str,
    ) -> dict:
        """Fetch a single page from the Crossref API with retry."""
        if self._client is None:
            raise RuntimeError("Use CrossrefClient as async context manager")

        # SSRN (10.2139) doesn't support from-posted-date but works with
        # from-created-date. Other prefixes use from-posted-date.
        if prefix in _CREATED_DATE_PREFIXES:
            date_filter = f"from-created-date:{from_date},until-created-date:{to_date}"
        else:
            date_filter = f"from-posted-date:{from_date},until-posted-date:{to_date}"

        params: dict = {
            "filter": f"prefix:{prefix},type:posted-content,{date_filter}",
            "rows": self.PAGE_SIZE,
            "cursor": cursor,
        }
        if self.email:
            params["mailto"] = self.email

        resp = await request_with_retry(
            self._client,
            self.BASE_URL,
            params=params,
            timeout=30.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            retry_on=(httpx.TimeoutException, httpx.RemoteProtocolError),
            source=f"crossref:{prefix}",
        )
        if resp is None:
            raise RuntimeError(f"Crossref returned unexpected None response for {prefix}")
        return resp.json()

    def _normalise(self, raw: dict, source_name: str) -> dict:
        """Map a Crossref work item to the common metadata schema."""
        titles = raw.get("title", [])
        title = titles[0].strip() if titles else ""

        authors = []
        for author in raw.get("author", []):
            family = author.get("family", "")
            given = author.get("given", "")
            if given:
                authors.append({"name": f"{family}, {given}"})
            else:
                authors.append({"name": family})

        abstract_raw = raw.get("abstract", "")
        abstract = _TAG_RE.sub("", abstract_raw).strip()

        # Parse date — try "posted" first, fall back to "created" (SSRN uses created)
        date_obj = raw.get("posted") or raw.get("created") or {}
        date_parts = date_obj.get("date-parts", [[]])
        parts = date_parts[0] if date_parts else []
        year = parts[0] if len(parts) >= 1 else 2000
        month = parts[1] if len(parts) >= 2 else 1
        day = parts[2] if len(parts) >= 3 else 1
        posted_date = date(year, month, day)

        # Extract version from DOI suffix (e.g., /v3)
        doi = raw.get("DOI", "")
        version = 1
        version_match = re.search(r"/v(\d+)$", doi)
        if version_match:
            version = int(version_match.group(1))

        source_server = _SOURCE_SERVER_MAP.get(source_name, SourceServer.RESEARCH_SQUARE)

        return {
            "doi": doi or None,
            "title": title,
            "authors": authors,
            "corresponding_author": None,
            "corresponding_institution": None,
            "abstract": abstract,
            "source_server": source_server,
            "posted_date": posted_date,
            "subject_category": None,
            "version": version,
            "full_text_url": None,
        }
