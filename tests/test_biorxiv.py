"""Tests for pipeline.ingest.biorxiv -- CSHL bioRxiv/medRxiv API client.

Covers fetch_papers pagination, error handling, rate limiting, and record
normalization for both biorxiv and medrxiv server modes.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from tests.conftest import make_api_response, make_collection, make_raw_record


class TestFetchPapers:
    """Tests for BiorxivClient.fetch_papers — pagination and HTTP handling."""

    @respx.mock
    async def test_fetch_single_page(self):
        """Fewer than PAGE_SIZE results should fetch a single page."""
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

    @respx.mock
    async def test_fetch_multiple_pages(self):
        """Results spanning multiple pages should paginate correctly."""
        page1 = make_collection(100, start_idx=0)
        page2 = make_collection(50, start_idx=100)

        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-02/0").mock(
            return_value=httpx.Response(200, json=make_api_response(page1, total=150))
        )
        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-02/100").mock(
            return_value=httpx.Response(200, json=make_api_response(page2, total=150))
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 2))]

        assert len(papers) == 150

    @respx.mock
    async def test_fetch_empty_results(self):
        """Empty response should yield no papers."""
        response = make_api_response([], total=0)

        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-02/0").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 2))]

        assert len(papers) == 0

    @respx.mock
    async def test_medrxiv_server_mode(self):
        """medRxiv mode should use the medrxiv API path."""
        collection = make_collection(2, server="medrxiv")
        response = make_api_response(collection, total=2)

        respx.get("https://api.biorxiv.org/details/medrxiv/2026-03-01/2026-03-02/0").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="medrxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 2))]

        assert len(papers) == 2
        assert all(p["source_server"] == "medrxiv" for p in papers)

    @respx.mock
    async def test_api_timeout_raises(self):
        """Timeout from the API should propagate after retries are exhausted."""
        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-02/0").mock(
            side_effect=httpx.ReadTimeout("read timed out")
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0, max_retries=1) as client:
            with pytest.raises(httpx.ReadTimeout):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 2))]

    @respx.mock
    async def test_api_server_error_retries(self):
        """503 should trigger retries; success on retry should return papers."""
        collection = make_collection(2)
        response = make_api_response(collection, total=2)

        route = respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-02/0")
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json=response),
        ]

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0, max_retries=3) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 2))]

        assert len(papers) == 2

    async def test_client_not_entered_raises(self):
        """Using client without async context manager should raise RuntimeError."""
        from pipeline.ingest.biorxiv import BiorxivClient

        client = BiorxivClient(server="biorxiv", request_delay=0)
        with pytest.raises(RuntimeError, match="async context manager"):
            _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 2))]


class TestNormalise:
    """Tests for BiorxivClient._normalise record normalization."""

    def _make_client(self, server: str = "biorxiv"):
        from pipeline.ingest.biorxiv import BiorxivClient

        return BiorxivClient(server=server, request_delay=0)

    def test_basic_field_mapping(self):
        client = self._make_client()
        raw = make_raw_record(
            doi="10.1101/2026.03.15.500001",
            title="  A Novel Approach to Protein Folding  ",
            authors="Smith, J.; Jones, A.",
            date_str="2026-03-15",
            version="2",
            category="bioinformatics",
        )
        result = client._normalise(raw)

        assert result["doi"] == "10.1101/2026.03.15.500001"
        assert result["title"] == "A Novel Approach to Protein Folding"
        assert result["authors"] == [{"name": "Smith, J."}, {"name": "Jones, A."}]
        assert result["posted_date"] == date(2026, 3, 15)
        assert result["version"] == 2
        assert result["source_server"] == "biorxiv"
        assert result["subject_category"] == "bioinformatics"

    def test_medrxiv_source_server(self):
        client = self._make_client(server="medrxiv")
        raw = make_raw_record(server="medrxiv")
        result = client._normalise(raw)
        assert result["source_server"] == "medrxiv"

    def test_html_entity_decoding(self):
        client = self._make_client()
        raw = make_raw_record(
            abstract="The structure shows &lt;50% occupancy &amp; high B-factors."
        )
        result = client._normalise(raw)
        assert "<50%" in result["abstract"]
        assert "& high" in result["abstract"]

    def test_empty_authors(self):
        client = self._make_client()
        raw = make_raw_record(authors="")
        result = client._normalise(raw)
        assert result["authors"] == []

    def test_single_author(self):
        client = self._make_client()
        raw = make_raw_record(authors="Solo, H.")
        result = client._normalise(raw)
        assert result["authors"] == [{"name": "Solo, H."}]

    def test_jatsxml_maps_to_full_text_url(self):
        client = self._make_client()
        raw = make_raw_record(
            jatsxml="https://www.biorxiv.org/content/10.1101/2026.03.15.500001v1.source.xml"
        )
        result = client._normalise(raw)
        assert result["full_text_url"] == (
            "https://www.biorxiv.org/content/10.1101/2026.03.15.500001v1.source.xml"
        )

    def test_missing_jatsxml(self):
        client = self._make_client()
        raw = make_raw_record()
        result = client._normalise(raw)
        assert result["full_text_url"] is None

    def test_corresponding_author_fields(self):
        client = self._make_client()
        raw = make_raw_record(
            author_corresponding="Alice Researcher",
            author_corresponding_institution="Stanford University",
        )
        result = client._normalise(raw)
        assert result["corresponding_author"] == "Alice Researcher"
        assert result["corresponding_institution"] == "Stanford University"

    def test_default_version_is_1(self):
        client = self._make_client()
        raw = make_raw_record(version="1")
        result = client._normalise(raw)
        assert result["version"] == 1

    @respx.mock
    async def test_pagination_stops_when_count_less_than_page_size(self):
        """Pagination should stop when returned count < PAGE_SIZE."""
        # Only 50 results total — should not request page 2
        collection = make_collection(50)
        response = make_api_response(collection, total=50)

        route = respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-02/0")
        route.mock(return_value=httpx.Response(200, json=response))

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 2))]

        assert len(papers) == 50
        # Only one HTTP call should have been made
        assert route.call_count == 1

    @respx.mock
    async def test_empty_messages_stops_iteration(self):
        """Empty messages array should stop pagination."""
        response = {"messages": [], "collection": []}

        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-02/0").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 2))]

        assert len(papers) == 0
