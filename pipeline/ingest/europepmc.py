"""Async client for the Europe PMC REST API.

Usage:
    async with EuropepmcClient() as client:
        async for paper in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30)):
            print(paper["title"])
"""

from __future__ import annotations

import asyncio
import html
from collections.abc import AsyncGenerator
from datetime import date

import httpx
import structlog

from pipeline.models import SourceServer

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
        cursor_mark = "*"
        while True:
            data = await self._fetch_page(from_date, to_date, cursor_mark)
            results = data.get("resultList", {}).get("result", [])
            if not results:
                break

            for raw in results:
                yield self._normalise(raw)

            next_cursor = data.get("nextCursorMark")
            if next_cursor is None or next_cursor == cursor_mark:
                break
            cursor_mark = next_cursor

            log.info(
                "page_fetched",
                source="europepmc",
                cursor=cursor_mark,
                hit_count=data.get("hitCount", 0),
                fetched_this_page=len(results),
            )

    async def _fetch_page(self, from_date: date, to_date: date, cursor_mark: str) -> dict:
        """Fetch a single page from the Europe PMC API with retry and backoff."""
        if self._client is None:
            raise RuntimeError("Use EuropepmcClient as async context manager")

        query = f"(FIRST_PDATE:[{from_date} TO {to_date}]) AND SRC:PPR"
        params = {
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": self.PAGE_SIZE,
            "cursorMark": cursor_mark,
        }

        for attempt in range(1, self.max_retries + 1):
            await asyncio.sleep(self.request_delay)
            try:
                resp = await self._client.get(self.BASE_URL, params=params, timeout=30.0)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 503):
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "rate_limited",
                        source="europepmc",
                        status=resp.status_code,
                        attempt=attempt,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                resp.raise_for_status()
            except httpx.TimeoutException:
                if attempt == self.max_retries:
                    raise
                backoff = min(2**attempt, 30)
                log.warning("timeout", source="europepmc", attempt=attempt, backoff=backoff)
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Europe PMC failed after {self.max_retries} retries")

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
            "source_server": SourceServer.EUROPEPMC,
            "posted_date": date.fromisoformat(raw["firstPublicationDate"]),
            "subject_category": None,
            "version": 1,
            "full_text_url": None,
        }
