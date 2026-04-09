"""Async client for the CSHL bioRxiv/medRxiv API.

Usage:
    async with BiorxivClient(server="biorxiv") as client:
        async for paper in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30)):
            print(paper["title"])
"""

from __future__ import annotations

import html
from collections.abc import AsyncGenerator
from datetime import date
from typing import Literal

import httpx
import structlog

from pipeline.http_retry import request_with_retry

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

    async def fetch_papers(self, from_date: date, to_date: date) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts, paginating through all results."""
        cursor = 0
        while True:
            data = await self._fetch_page(from_date, to_date, cursor)
            messages = data.get("messages", [{}])
            if not messages:
                break

            msg = messages[0]
            total = int(msg.get("total", 0))
            count = int(msg.get("count", 0))

            for raw in data.get("collection", []):
                yield self._normalise(raw)

            cursor += self.PAGE_SIZE
            if count < self.PAGE_SIZE or cursor >= total:
                break

            log.info(
                "page_fetched",
                server=self.server,
                cursor=cursor,
                total=total,
                fetched_this_page=count,
            )

    # -- Internal ------------------------------------------------------------

    async def _fetch_page(self, from_date: date, to_date: date, cursor: int) -> dict:
        """Fetch a single page from the API with retry and backoff."""
        if self._client is None:
            raise RuntimeError("Use BiorxivClient as async context manager")
        url = f"{self.BASE_URL}/{self.server}/{from_date}/{to_date}/{cursor}"

        resp = await request_with_retry(
            self._client,
            url,
            timeout=60.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            retry_on=(httpx.TimeoutException, httpx.RemoteProtocolError),
            source=self.server,
        )
        assert resp is not None  # none_on_404 not set, so always Response or raise
        return resp.json()

    def _normalise(self, raw: dict) -> dict:
        """Map a raw CSHL API record to the common metadata schema."""
        authors_str = raw.get("authors", "")
        authors_list = [{"name": a.strip()} for a in authors_str.split(";") if a.strip()]

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
