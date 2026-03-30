"""Async client for the Europe PMC REST API.

Usage:
    async with EuropepmcClient() as client:
        async for paper in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30)):
            print(paper["title"])
"""

from __future__ import annotations

import html
from collections.abc import AsyncGenerator
from datetime import date

import httpx
import structlog

log = structlog.get_logger()


class EuropepmcClient:
    """Async client for Europe PMC preprint search."""

    BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    PAGE_SIZE = 1000

    def __init__(
        self,
        request_delay: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> EuropepmcClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # -- Public API ----------------------------------------------------------

    async def fetch_papers(self, from_date: date, to_date: date) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts, paginating through all results."""
        raise NotImplementedError  # Implemented in Task 4

    # -- Internal ------------------------------------------------------------

    def _normalise(self, raw: dict) -> dict:
        """Map a Europe PMC record to the common metadata schema."""
        author_str = raw.get("authorString", "")
        authors_list = [{"name": a.strip()} for a in author_str.split(", ") if a.strip()]

        return {
            "doi": raw.get("doi"),
            "title": raw.get("title", "").strip(),
            "authors": authors_list,
            "corresponding_author": None,
            "corresponding_institution": None,
            "abstract": html.unescape(raw.get("abstractText", "")),
            "source_server": "europepmc",
            "posted_date": date.fromisoformat(raw["firstPublicationDate"]),
            "subject_category": None,
            "version": 1,
            "full_text_url": None,
        }
