"""Async client for the Semantic Scholar Academic Graph API.

Usage:
    async with SemanticScholarClient(api_key="...") as client:
        result = await client.lookup("10.1234/some-doi")
        if result:
            print(result["first_author_h_index"])
"""

from __future__ import annotations

import httpx
import structlog

from pipeline.http_retry import request_with_retry

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
        if self._client is None:
            raise RuntimeError("Use SemanticScholarClient as async context manager")

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

        resp = await request_with_retry(
            self._client,
            url,
            params=params,
            timeout=30.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            none_on_404=True,
            source="semantic_scholar",
        )
        if resp is None:
            return None
        return resp.json()

    async def _fetch_author(self, author_id: str) -> dict | None:
        """Fetch author detail. Returns None on any error."""
        url = f"{BASE_URL}/author/{author_id}"
        params = {"fields": "name,hIndex,citationCount,paperCount"}
        try:
            resp = await request_with_retry(
                self._client,
                url,
                params=params,
                timeout=30.0,
                request_delay=self.request_delay,
                max_retries=self.max_retries,
                none_on_404=True,
                source="semantic_scholar",
            )
            if resp is None:
                return None
            return resp.json()
        except Exception as exc:
            log.debug("s2_author_error", author_id=author_id, error=str(exc))
        return None
