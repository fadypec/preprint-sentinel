"""Async client for the Semantic Scholar Academic Graph API.

Usage:
    async with SemanticScholarClient(api_key="...") as client:
        result = await client.lookup("10.1234/some-doi")
        if result:
            print(result["first_author_h_index"])
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

log = structlog.get_logger()

BASE_URL = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarClient:
    """Async client for the Semantic Scholar API."""

    def __init__(
        self,
        api_key: str = "",
        request_delay: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> SemanticScholarClient:
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        self._client = httpx.AsyncClient(headers=headers)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    async def lookup(self, doi: str) -> dict | None:
        """Look up a paper by DOI and return enrichment data, or None."""
        assert self._client is not None, "Use SemanticScholarClient as async context manager"

        paper = await self._fetch_paper(doi)
        if paper is None:
            return None

        s2_paper_id = paper.get("paperId", "")
        tldr_obj = paper.get("tldr")
        tldr = tldr_obj.get("text") if tldr_obj else None
        citation_count = paper.get("citationCount", 0)
        influential_citation_count = paper.get("influentialCitationCount", 0)

        # Fetch first author details
        first_author_h_index = None
        first_author_paper_count = None
        first_author_citation_count = None

        authors = paper.get("authors", [])
        if authors:
            first_author_id = authors[0].get("authorId")
            if first_author_id:
                author_detail = await self._fetch_author(first_author_id)
                if author_detail is not None:
                    first_author_h_index = author_detail.get("hIndex")
                    first_author_paper_count = author_detail.get("paperCount")
                    first_author_citation_count = author_detail.get("citationCount")

        return {
            "s2_paper_id": s2_paper_id,
            "tldr": tldr,
            "citation_count": citation_count,
            "influential_citation_count": influential_citation_count,
            "first_author_h_index": first_author_h_index,
            "first_author_paper_count": first_author_paper_count,
            "first_author_citation_count": first_author_citation_count,
        }

    async def _fetch_paper(self, doi: str) -> dict | None:
        """Fetch paper data from Semantic Scholar by DOI."""
        url = f"{BASE_URL}/paper/DOI:{doi}"
        params = {
            "fields": "title,tldr,citationCount,influentialCitationCount,authors",
        }

        for attempt in range(1, self.max_retries + 1):
            await asyncio.sleep(self.request_delay)
            try:
                resp = await self._client.get(url, params=params, timeout=30.0)
                if resp.status_code == 404:
                    return None
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 503):
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "rate_limited",
                        source="semantic_scholar",
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
                log.warning(
                    "timeout", source="semantic_scholar", attempt=attempt, backoff=backoff
                )
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Semantic Scholar failed after {self.max_retries} retries: {doi}")

    async def _fetch_author(self, author_id: str) -> dict | None:
        """Fetch author detail. Returns None on any error."""
        url = f"{BASE_URL}/author/{author_id}"
        params = {"fields": "name,hIndex,citationCount,paperCount"}
        try:
            await asyncio.sleep(self.request_delay)
            resp = await self._client.get(url, params=params, timeout=30.0)
            if resp.status_code == 200:
                return resp.json()
        except httpx.HTTPError as exc:
            log.debug("s2_author_error", author_id=author_id, error=str(exc))
        except Exception as exc:
            log.warning("s2_author_unexpected_error", author_id=author_id, error=str(exc))
        return None
