"""Unpaywall API client — find open access full-text URLs by DOI.

Usage:
    async with UnpaywallClient(email="you@example.com") as client:
        result = await client.lookup("10.1234/some-doi")
        if result:
            print(result.url, result.content_type)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger()

BASE_URL = "https://api.unpaywall.org/v2"

# Known XML hosts (URLs from these domains are likely JATS XML)
_XML_HOSTS = {"europepmc.org", "ncbi.nlm.nih.gov", "ebi.ac.uk"}


@dataclass(frozen=True)
class UnpaywallResult:
    """Result of an Unpaywall DOI lookup."""

    url: str
    content_type: str  # "xml", "html", "pdf"
    host_type: str  # "publisher", "repository"


def _classify_url(url: str) -> str:
    """Classify a URL as xml, pdf, or html based on URL patterns."""
    lower = url.lower()
    if lower.endswith(".xml") or ("fulltext" in lower and "xml" in lower):
        return "xml"
    if lower.endswith(".pdf") or "/pdf/" in lower:
        return "pdf"
    for host in _XML_HOSTS:
        if host in lower and "xml" in lower:
            return "xml"
    return "html"


class UnpaywallClient:
    """Async client for the Unpaywall API."""

    def __init__(
        self,
        email: str,
        request_delay: float = 0.1,
        max_retries: int = 3,
    ) -> None:
        self.email = email
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> UnpaywallClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    async def lookup(self, doi: str) -> UnpaywallResult | None:
        """Look up a DOI and return the best OA location, or None."""
        assert self._client is not None, "Use UnpaywallClient as async context manager"

        url = f"{BASE_URL}/{doi}"
        params = {"email": self.email}

        for attempt in range(1, self.max_retries + 1):
            await asyncio.sleep(self.request_delay)
            try:
                resp = await self._client.get(url, params=params, timeout=30.0)
                if resp.status_code == 404:
                    return None
                if resp.status_code == 200:
                    return self._parse_response(resp.json())
                if resp.status_code in (429, 503):
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "rate_limited",
                        source="unpaywall",
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
                log.warning("timeout", source="unpaywall", attempt=attempt, backoff=backoff)
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Unpaywall failed after {self.max_retries} retries: {doi}")

    def _parse_response(self, data: dict) -> UnpaywallResult | None:
        """Extract best OA location from Unpaywall response."""
        if not data.get("is_oa"):
            return None

        location = data.get("best_oa_location")
        if not location:
            return None

        url = location.get("url") or location.get("url_for_landing_page")
        if not url:
            return None

        return UnpaywallResult(
            url=url,
            content_type=_classify_url(url),
            host_type=location.get("host_type", "unknown"),
        )
