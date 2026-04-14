"""Async client for the Zenodo REST API.

Usage:
    async with ZenodoClient() as client:
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

_TAG_RE = re.compile(r"<[^>]+>")


class ZenodoClient:
    """Async client for Zenodo preprint search."""

    BASE_URL = "https://zenodo.org/api/records"
    PAGE_SIZE = 100

    def __init__(
        self,
        request_delay: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ZenodoClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # -- Public API ----------------------------------------------------------

    async def fetch_papers(self, from_date: date, to_date: date) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts from Zenodo preprints."""
        page = 1
        while True:
            data = await self._fetch_page(from_date, to_date, page)
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break

            for hit in hits:
                yield self._normalise(hit)

            if len(hits) < self.PAGE_SIZE:
                break
            page += 1

            log.info(
                "page_fetched",
                source="zenodo",
                page=page,
                total=data.get("hits", {}).get("total", 0),
                fetched_this_page=len(hits),
            )

    # -- Internal ------------------------------------------------------------

    async def _fetch_page(self, from_date: date, to_date: date, page: int) -> dict:
        """Fetch a single page from the Zenodo API with retry."""
        if self._client is None:
            raise RuntimeError("Use ZenodoClient as async context manager")

        # Build URL with q= directly to avoid httpx encoding [ ] which Zenodo rejects
        q_value = f"created:[{from_date} TO {to_date}]"
        url = f"{self.BASE_URL}?q={q_value}"
        params = {
            "type": "publication",
            "subtype": "preprint",
            "size": self.PAGE_SIZE,
            "page": page,
            "sort": "-created",
        }

        resp = await request_with_retry(
            self._client,
            url,
            params=params,
            timeout=30.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            retry_on=(httpx.TimeoutException, httpx.RemoteProtocolError),
            source="zenodo",
        )
        if resp is None:
            raise RuntimeError("Zenodo returned unexpected None response")
        return resp.json()

    def _normalise(self, hit: dict) -> dict:
        """Map a Zenodo record hit to the common metadata schema."""
        metadata = hit.get("metadata", {})

        title = metadata.get("title", "").strip()

        creators = metadata.get("creators", [])
        authors = [{"name": c.get("name", "")} for c in creators]

        description_raw = metadata.get("description", "")
        abstract = _TAG_RE.sub("", description_raw).strip()

        pub_date_str = metadata.get("publication_date", "")
        posted_date = date.fromisoformat(pub_date_str) if pub_date_str else date.today()

        subjects = metadata.get("subjects", [])
        subject_category = subjects[0].get("term") if subjects else None

        return {
            "doi": hit.get("doi"),
            "title": title,
            "authors": authors,
            "corresponding_author": None,
            "corresponding_institution": None,
            "abstract": abstract,
            "source_server": SourceServer.ZENODO,
            "posted_date": posted_date,
            "subject_category": subject_category,
            "version": 1,
            "full_text_url": None,
        }
