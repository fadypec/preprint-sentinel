"""Crossref DOI metadata lookup for funder information.

Queries Crossref's works API by DOI to extract funder names and
grant IDs. This supplements OpenAlex funder data, which may be
incomplete for newer papers.

Usage:
    async with CrossrefEnrichmentClient(email="you@example.com") as client:
        data = await client.lookup("10.1101/2026.03.15.500001")
        # -> {"funders": [{"name": "NIH", "doi": "10.13039/100000002", "award": ["R01..."]}]}
"""

from __future__ import annotations

import httpx
import structlog

from pipeline.http_retry import request_with_retry

log = structlog.get_logger()


class CrossrefEnrichmentClient:
    """Fetch funder metadata from Crossref for a given DOI."""

    BASE_URL = "https://api.crossref.org/works"

    def __init__(
        self,
        email: str = "",
        request_delay: float = 1.0,
        max_retries: int = 3,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.email = email
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._external_client = http
        self._client: httpx.AsyncClient | None = http

    async def __aenter__(self) -> CrossrefEnrichmentClient:
        if self._external_client is None:
            self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._external_client is None and self._client:
            await self._client.aclose()
        self._client = None

    async def lookup(self, doi: str) -> dict | None:
        """Look up a DOI and extract funder information.

        Returns dict with "funders" key, or None if DOI not found.
        """
        if not doi or self._client is None:
            return None

        url = f"{self.BASE_URL}/{doi}"
        params: dict = {}
        if self.email:
            params["mailto"] = self.email

        resp = await request_with_retry(
            self._client,
            url,
            params=params,
            timeout=15.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            retry_on=(httpx.TimeoutException, httpx.RemoteProtocolError),
            none_on_404=True,
            source="crossref_enrichment",
        )

        if resp is None:
            return None

        data = resp.json()
        work = data.get("message", {})

        # Extract funder information
        raw_funders = work.get("funder", [])
        funders = []
        for f in raw_funders:
            funder = {
                "name": f.get("name", ""),
                "doi": f.get("DOI"),
                "award": f.get("award", []),
            }
            if funder["name"]:
                funders.append(funder)

        if not funders:
            return None

        return {"funders": funders}
