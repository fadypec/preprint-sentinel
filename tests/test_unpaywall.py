"""Tests for pipeline.fulltext.unpaywall — Unpaywall API client."""

from __future__ import annotations

import httpx
import respx


def _oa_response(
    url: str = "https://europepmc.org/articles/PMC123/full.xml",
    host_type: str = "repository",
) -> dict:
    """Build a mock Unpaywall API response."""
    return {
        "doi": "10.1234/test",
        "is_oa": True,
        "best_oa_location": {
            "url": url,
            "url_for_pdf": None,
            "url_for_landing_page": url,
            "host_type": host_type,
        },
    }


class TestLookup:
    """Tests for UnpaywallClient.lookup."""

    @respx.mock
    async def test_successful_xml_lookup(self):
        from pipeline.fulltext.unpaywall import UnpaywallClient

        respx.get("https://api.unpaywall.org/v2/10.1234/test").mock(
            return_value=httpx.Response(
                200,
                json=_oa_response(url="https://europepmc.org/articles/PMC123/fullTextXML"),
            )
        )

        async with UnpaywallClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        assert result.url == "https://europepmc.org/articles/PMC123/fullTextXML"
        assert result.content_type == "xml"

    @respx.mock
    async def test_html_url_detected(self):
        from pipeline.fulltext.unpaywall import UnpaywallClient

        respx.get("https://api.unpaywall.org/v2/10.1234/test").mock(
            return_value=httpx.Response(
                200, json=_oa_response(url="https://publisher.com/article/12345")
            )
        )

        async with UnpaywallClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        assert result.content_type == "html"

    @respx.mock
    async def test_pdf_url_detected(self):
        from pipeline.fulltext.unpaywall import UnpaywallClient

        respx.get("https://api.unpaywall.org/v2/10.1234/test").mock(
            return_value=httpx.Response(
                200, json=_oa_response(url="https://publisher.com/article/12345.pdf")
            )
        )

        async with UnpaywallClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/test")

        assert result is not None
        assert result.content_type == "pdf"

    @respx.mock
    async def test_not_found_returns_none(self):
        from pipeline.fulltext.unpaywall import UnpaywallClient

        respx.get("https://api.unpaywall.org/v2/10.1234/missing").mock(
            return_value=httpx.Response(404)
        )

        async with UnpaywallClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/missing")

        assert result is None

    @respx.mock
    async def test_not_oa_returns_none(self):
        from pipeline.fulltext.unpaywall import UnpaywallClient

        respx.get("https://api.unpaywall.org/v2/10.1234/closed").mock(
            return_value=httpx.Response(
                200,
                json={
                    "doi": "10.1234/closed",
                    "is_oa": False,
                    "best_oa_location": None,
                },
            )
        )

        async with UnpaywallClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/closed")

        assert result is None

    @respx.mock
    async def test_retry_on_429(self):
        from pipeline.fulltext.unpaywall import UnpaywallClient

        route = respx.get("https://api.unpaywall.org/v2/10.1234/retry").mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=_oa_response()),
            ]
        )

        async with UnpaywallClient(email="test@test.com", request_delay=0) as client:
            result = await client.lookup("10.1234/retry")

        assert result is not None
        assert route.call_count == 2
