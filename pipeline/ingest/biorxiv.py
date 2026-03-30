"""Async client for the CSHL bioRxiv/medRxiv API.

Usage:
    async with BiorxivClient(server="biorxiv") as client:
        async for paper in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30)):
            print(paper["title"])
"""

from __future__ import annotations

import asyncio
import html
from datetime import date
from typing import TYPE_CHECKING, AsyncGenerator, Literal

import httpx
import structlog

if TYPE_CHECKING:
    pass

log = structlog.get_logger()


class BiorxivClient:
    """Async client for bioRxiv and medRxiv via the shared CSHL API."""

    BASE_URL = "https://api.biorxiv.org/details"
    PAGE_SIZE = 100

    def __init__(
        self,
        server: Literal["biorxiv", "medrxiv"],
        request_delay: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.server = server
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> BiorxivClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # -- Public API ----------------------------------------------------------

    async def fetch_papers(
        self, from_date: date, to_date: date
    ) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts, paginating through all results."""
        # Implemented in Task 7
        raise NotImplementedError
        yield  # Make this a generator  # noqa: E711

    # -- Internal ------------------------------------------------------------

    async def _fetch_page(
        self, from_date: date, to_date: date, cursor: int
    ) -> dict:
        """Fetch a single page from the API with retry and backoff."""
        # Implemented in Task 7
        raise NotImplementedError

    def _normalise(self, raw: dict) -> dict:
        """Map a raw CSHL API record to the common metadata schema."""
        authors_str = raw.get("authors", "")
        authors_list = [
            {"name": a.strip()} for a in authors_str.split(";") if a.strip()
        ]

        return {
            "doi": raw.get("doi"),
            "title": raw.get("title", "").strip(),
            "authors": authors_list,
            "corresponding_author": raw.get("author_corresponding"),
            "corresponding_institution": raw.get("author_corresponding_institution"),
            "abstract": html.unescape(raw.get("abstract", "")),
            "source_server": self.server,
            "posted_date": date.fromisoformat(raw["date"]),
            "subject_category": raw.get("category"),
            "version": int(raw.get("version", 1)),
            "full_text_url": raw.get("jatsxml"),
        }
