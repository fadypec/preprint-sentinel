"""Tests for pipeline.ingest.europepmc — Europe PMC API client."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from tests.conftest import make_europepmc_record, make_europepmc_response


class TestNormalise:
    """Tests for EuropepmcClient._normalise field mapping."""

    def _make_client(self):
        from pipeline.ingest.europepmc import EuropepmcClient

        return EuropepmcClient(request_delay=0)

    def test_basic_field_mapping(self):
        client = self._make_client()
        raw = make_europepmc_record(
            doi="10.1101/2026.03.15.500001",
            title="  Test Title With Spaces  ",
            author_string="Smith J, Jones A, Brown BC",
            first_pub_date="2026-03-15",
        )
        result = client._normalise(raw)

        assert result["doi"] == "10.1101/2026.03.15.500001"
        assert result["title"] == "Test Title With Spaces"  # stripped
        assert result["authors"] == [
            {"name": "Smith J"},
            {"name": "Jones A"},
            {"name": "Brown BC"},
        ]
        assert result["posted_date"] == date(2026, 3, 15)
        assert result["source_server"] == "europepmc"
        assert result["version"] == 1

    def test_html_entity_decoding_in_abstract(self):
        client = self._make_client()
        raw = make_europepmc_record(
            abstract="The 1.8 &Aring; structure shows &lt;50% occupancy &amp; high B-factors."
        )
        result = client._normalise(raw)
        assert "\u00c5" in result["abstract"]  # Angstrom symbol decoded
        assert "<50%" in result["abstract"]
        assert "& high" in result["abstract"]

    def test_fields_not_available_from_search(self):
        """Europe PMC search doesn't provide these fields — all should be None."""
        client = self._make_client()
        raw = make_europepmc_record()
        result = client._normalise(raw)
        assert result["corresponding_author"] is None
        assert result["corresponding_institution"] is None
        assert result["subject_category"] is None
        assert result["full_text_url"] is None

    def test_empty_author_string(self):
        client = self._make_client()
        raw = make_europepmc_record(author_string="")
        result = client._normalise(raw)
        assert result["authors"] == []

    def test_single_author(self):
        client = self._make_client()
        raw = make_europepmc_record(author_string="Solo H")
        result = client._normalise(raw)
        assert result["authors"] == [{"name": "Solo H"}]

    def test_doi_none_when_missing(self):
        client = self._make_client()
        raw = make_europepmc_record(doi=None)
        result = client._normalise(raw)
        assert result["doi"] is None


class TestFetch:
    """Tests for EuropepmcClient.fetch_papers — HTTP fetch + pagination."""

    SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    @respx.mock
    async def test_fetch_single_page(self):
        """Fetch results that fit in one page — no pagination needed."""
        records = [
            make_europepmc_record(ppr_id=f"PPR{i}", doi=f"10.1101/2026.03.01.{i}") for i in range(3)
        ]
        page1 = make_europepmc_response(records, hit_count=3, next_cursor="same_cursor")
        page2 = make_europepmc_response([], hit_count=3, next_cursor="same_cursor")

        respx.get(self.SEARCH_URL).mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 3
        assert papers[0]["doi"] == "10.1101/2026.03.01.0"
        assert papers[0]["source_server"] == "europepmc"

    @respx.mock
    async def test_fetch_cursor_pagination(self):
        """Fetch results across two pages using cursor-based pagination."""
        page1_records = [
            make_europepmc_record(ppr_id=f"PPR{i}", doi=f"10.1101/2026.03.01.{i}") for i in range(3)
        ]
        page2_records = [
            make_europepmc_record(ppr_id=f"PPR{i}", doi=f"10.1101/2026.03.01.{i}")
            for i in range(3, 5)
        ]
        page1 = make_europepmc_response(page1_records, hit_count=5, next_cursor="cursor_page2")
        page2 = make_europepmc_response(page2_records, hit_count=5, next_cursor="cursor_page2")

        route = respx.get(self.SEARCH_URL).mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 5))]

        assert len(papers) == 5
        assert route.call_count == 2

    @respx.mock
    async def test_fetch_empty_result(self):
        """No papers found — yields nothing."""
        response = make_europepmc_response([], hit_count=0)
        respx.get(self.SEARCH_URL).mock(return_value=httpx.Response(200, json=response))

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 1, 1), date(2026, 1, 1))]

        assert len(papers) == 0


class TestRetry:
    """Tests for EuropepmcClient retry and error handling."""

    SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    @respx.mock
    async def test_429_retries_then_succeeds(self):
        records = [make_europepmc_record()]
        ok_response = make_europepmc_response(records, next_cursor="done")
        empty_response = make_europepmc_response([], next_cursor="done")

        route = respx.get(self.SEARCH_URL).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=ok_response),
                httpx.Response(200, json=empty_response),
            ]
        )

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 1
        assert route.call_count >= 2

    @respx.mock
    async def test_503_retries_then_succeeds(self):
        records = [make_europepmc_record()]
        ok_response = make_europepmc_response(records, next_cursor="done")
        empty_response = make_europepmc_response([], next_cursor="done")

        respx.get(self.SEARCH_URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json=ok_response),
                httpx.Response(200, json=empty_response),
            ]
        )

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 1

    @respx.mock
    async def test_timeout_retries_then_succeeds(self):
        records = [make_europepmc_record()]
        ok_response = make_europepmc_response(records, next_cursor="done")
        empty_response = make_europepmc_response([], next_cursor="done")

        respx.get(self.SEARCH_URL).mock(
            side_effect=[
                httpx.TimeoutException("connect timeout"),
                httpx.Response(200, json=ok_response),
                httpx.Response(200, json=empty_response),
            ]
        )

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 1

    @respx.mock
    async def test_all_retries_exhausted_raises(self):
        respx.get(self.SEARCH_URL).mock(return_value=httpx.Response(429))

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0, max_retries=2) as client:
            with pytest.raises(RuntimeError, match="failed after 2 retries"):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

    @respx.mock
    async def test_non_retryable_error_raises_immediately(self):
        route = respx.get(self.SEARCH_URL).mock(return_value=httpx.Response(404))

        from pipeline.ingest.europepmc import EuropepmcClient

        async with EuropepmcClient(request_delay=0) as client:
            with pytest.raises(httpx.HTTPStatusError):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert route.call_count == 1
