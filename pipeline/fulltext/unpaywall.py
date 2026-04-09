"""Unpaywall API client — find open access full-text URLs by DOI.

Usage:
    async with UnpaywallClient(email="you@example.com") as client:
        result = await client.lookup("10.1234/some-doi")
        if result:
            print(result.url, result.content_type)
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

from pipeline.http_retry import request_with_retry

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
        if self._client is None:
            raise RuntimeError("Use UnpaywallClient as async context manager")

        url = f"{BASE_URL}/{doi}"
        params = {"email": self.email}

        resp = await request_with_retry(
            self._client,
            url,
            params=params,
            timeout=30.0,
            request_delay=self.request_delay,
            max_retries=self.max_retries,
            none_on_404=True,
            source="unpaywall",
        )
        if resp is None:
            return None
        return self._parse_response(resp.json())

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
