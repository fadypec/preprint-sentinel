"""Tests for pipeline.ingest.biorxiv — CSHL API client."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from tests.conftest import make_api_response, make_collection, make_raw_record


class TestNormalise:
    """Tests for BiorxivClient._normalise field mapping."""

    def _make_client(self, server: str = "biorxiv"):
        from pipeline.ingest.biorxiv import BiorxivClient

        return BiorxivClient(server=server, request_delay=0)

    def test_basic_field_mapping(self):
        client = self._make_client()
        raw = make_raw_record(
            doi="10.1101/2026.03.15.500001",
            title="  Test Title With Spaces  ",
            authors="Smith, J.; Jones, A.; Brown, B.",
            date_str="2026-03-15",
            version="2",
            category="microbiology",
            server="biorxiv",
        )
        result = client._normalise(raw)

        assert result["doi"] == "10.1101/2026.03.15.500001"
        assert result["title"] == "Test Title With Spaces"  # stripped
        assert result["authors"] == [
            {"name": "Smith, J."},
            {"name": "Jones, A."},
            {"name": "Brown, B."},
        ]
        assert result["posted_date"] == date(2026, 3, 15)
        assert result["version"] == 2
        assert result["source_server"] == "biorxiv"
        assert result["subject_category"] == "microbiology"

    def test_html_entity_decoding_in_abstract(self):
        client = self._make_client()
        raw = make_raw_record(
            abstract=(
                "The 1.8 &Aring; structure of ACE2 shows &lt;50% occupancy &amp; high B-factors."
            )
        )
        result = client._normalise(raw)
        assert "\u00c5" in result["abstract"]  # Angstrom symbol decoded
        assert "<50%" in result["abstract"]
        assert "& high" in result["abstract"]

    def test_corresponding_author_fields(self):
        client = self._make_client()
        raw = make_raw_record(
            author_corresponding="Sanjay Patel",
            author_corresponding_institution="Scripps Research Institute",
        )
        result = client._normalise(raw)
        assert result["corresponding_author"] == "Sanjay Patel"
        assert result["corresponding_institution"] == "Scripps Research Institute"

    def test_medrxiv_source_server(self):
        client = self._make_client(server="medrxiv")
        raw = make_raw_record(server="medrxiv")
        result = client._normalise(raw)
        assert result["source_server"] == "medrxiv"

    def test_jatsxml_maps_to_full_text_url(self):
        client = self._make_client()
        raw = make_raw_record(
            jatsxml="https://www.biorxiv.org/content/10.1101/2026.03.15.500001v1.source.xml"
        )
        result = client._normalise(raw)
        assert (
            result["full_text_url"]
            == "https://www.biorxiv.org/content/10.1101/2026.03.15.500001v1.source.xml"
        )

    def test_missing_jatsxml_gives_none(self):
        client = self._make_client()
        raw = make_raw_record()  # no jatsxml key
        result = client._normalise(raw)
        assert result["full_text_url"] is None

    def test_empty_authors_string(self):
        client = self._make_client()
        raw = make_raw_record(authors="")
        result = client._normalise(raw)
        assert result["authors"] == []

    def test_single_author(self):
        client = self._make_client()
        raw = make_raw_record(authors="Solo, H.")
        result = client._normalise(raw)
        assert result["authors"] == [{"name": "Solo, H."}]


class TestFetch:
    """Tests for BiorxivClient.fetch_papers — HTTP fetch + pagination."""

    @respx.mock
    async def test_fetch_single_page(self):
        """Fetch fewer than 100 results — single page, no pagination."""
        collection = make_collection(3)
        response = make_api_response(collection, total=3)

        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-02/0").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 2))]

        assert len(papers) == 3
        assert papers[0]["doi"] == "10.1101/2026.03.01.100000"
        assert papers[0]["source_server"] == "biorxiv"

    @respx.mock
    async def test_fetch_multiple_pages(self):
        """Fetch 250 results — should paginate across 3 pages (100+100+50)."""
        page1 = make_api_response(make_collection(100, start_idx=0), total=250)
        page2 = make_api_response(make_collection(100, start_idx=100), total=250)
        page3 = make_api_response(make_collection(50, start_idx=200), total=250)

        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-30/0").mock(
            return_value=httpx.Response(200, json=page1)
        )
        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-30/100").mock(
            return_value=httpx.Response(200, json=page2)
        )
        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-30/200").mock(
            return_value=httpx.Response(200, json=page3)
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]

        assert len(papers) == 250
        assert papers[0]["doi"] == "10.1101/2026.03.01.100000"
        assert papers[200]["doi"] == "10.1101/2026.03.01.100200"

    @respx.mock
    async def test_fetch_empty_result(self):
        """No papers found for date range — yields nothing."""
        response = make_api_response([], total=0)

        respx.get("https://api.biorxiv.org/details/biorxiv/2026-01-01/2026-01-01/0").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 1, 1), date(2026, 1, 1))]

        assert len(papers) == 0

    @respx.mock
    async def test_medrxiv_url(self):
        """medRxiv client hits /medrxiv/ endpoint."""
        response = make_api_response(make_collection(1, server="medrxiv"), total=1)

        route = respx.get("https://api.biorxiv.org/details/medrxiv/2026-03-01/2026-03-01/0").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="medrxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert route.called
        assert len(papers) == 1


class TestRetry:
    """Tests for BiorxivClient retry and error handling."""

    @respx.mock
    async def test_rate_limit_429_retries_then_succeeds(self):
        collection = make_collection(1)
        ok_response = make_api_response(collection, total=1)
        url = "https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-01/0"
        route = respx.get(url).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=ok_response),
            ]
        )
        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]
        assert len(papers) == 1
        assert route.call_count == 2

    @respx.mock
    async def test_503_retries_then_succeeds(self):
        collection = make_collection(1)
        ok_response = make_api_response(collection, total=1)
        url = "https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-01/0"
        route = respx.get(url).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json=ok_response),
            ]
        )
        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]
        assert len(papers) == 1
        assert route.call_count == 2

    @respx.mock
    async def test_timeout_retries_then_succeeds(self):
        collection = make_collection(1)
        ok_response = make_api_response(collection, total=1)
        url = "https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-01/0"
        route = respx.get(url).mock(
            side_effect=[
                httpx.TimeoutException("connect timeout"),
                httpx.Response(200, json=ok_response),
            ]
        )
        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]
        assert len(papers) == 1
        assert route.call_count == 2

    @respx.mock
    async def test_all_retries_exhausted_raises(self):
        url = "https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-01/0"
        respx.get(url).mock(return_value=httpx.Response(429))
        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0, max_retries=2) as client:
            with pytest.raises(RuntimeError, match="Failed after 2 retries"):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

    @respx.mock
    async def test_non_retryable_error_raises_immediately(self):
        url = "https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-01/0"
        route = respx.get(url).mock(return_value=httpx.Response(404))
        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            with pytest.raises(httpx.HTTPStatusError):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]
        assert route.call_count == 1
