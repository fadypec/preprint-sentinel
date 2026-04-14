"""Tests for pipeline.ingest.crossref — Crossref API client."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx


def _make_client(**kwargs):
    from pipeline.ingest.crossref import CrossrefClient

    return CrossrefClient(request_delay=0, **kwargs)


def _make_crossref_item(
    doi: str = "10.21203/rs.3.rs-1234567/v1",
    title: str = "Test Paper",
    given: str = "Alice",
    family: str = "Smith",
    abstract: str = "<p>Test abstract.</p>",
    posted_parts: list | None = None,
    subtype: str = "preprint",
) -> dict:
    """Create a Crossref work item matching the real API format."""
    if posted_parts is None:
        posted_parts = [[2026, 3, 15]]
    item: dict = {
        "DOI": doi,
        "title": [title],
        "author": [{"given": given, "family": family}],
        "abstract": abstract,
        "posted": {"date-parts": posted_parts},
        "subtype": subtype,
    }
    return item


def _make_crossref_response(
    items: list[dict],
    total: int | None = None,
    next_cursor: str | None = None,
) -> dict:
    """Wrap items in the Crossref API response envelope."""
    msg: dict = {
        "total-results": total if total is not None else len(items),
        "items": items,
    }
    if next_cursor:
        msg["next-cursor"] = next_cursor
    return {"status": "ok", "message-type": "work-list", "message": msg}


class TestNormalise:
    """Tests for CrossrefClient._normalise field mapping."""

    def test_basic_field_mapping(self):
        client = _make_client()
        item = _make_crossref_item(
            doi="10.21203/rs.3.rs-1234567/v1",
            title="  Research Square Paper  ",
            given="Alice",
            family="Smith",
            abstract="<p>An abstract with <b>HTML</b> tags.</p>",
            posted_parts=[[2026, 3, 15]],
        )
        result = client._normalise(item, "research_square")

        assert result["doi"] == "10.21203/rs.3.rs-1234567/v1"
        assert result["title"] == "Research Square Paper"
        assert result["authors"] == [{"name": "Smith, Alice"}]
        assert result["abstract"] == "An abstract with HTML tags."
        assert result["posted_date"] == date(2026, 3, 15)
        assert result["source_server"] == "research_square"
        assert result["version"] == 1

    def test_chemrxiv_source_server(self):
        client = _make_client()
        item = _make_crossref_item(doi="10.26434/chemrxiv-2026-abc")
        result = client._normalise(item, "chemrxiv")
        assert result["source_server"] == "chemrxiv"

    def test_ssrn_source_server(self):
        client = _make_client()
        item = _make_crossref_item(doi="10.2139/ssrn.4000001")
        result = client._normalise(item, "ssrn")
        assert result["source_server"] == "ssrn"

    def test_multiple_authors(self):
        client = _make_client()
        item = _make_crossref_item()
        item["author"] = [
            {"given": "Alice", "family": "Smith"},
            {"given": "Bob", "family": "Jones"},
            {"family": "Consortium"},  # no given name
        ]
        result = client._normalise(item, "research_square")
        assert result["authors"] == [
            {"name": "Smith, Alice"},
            {"name": "Jones, Bob"},
            {"name": "Consortium"},
        ]

    def test_missing_abstract(self):
        client = _make_client()
        item = _make_crossref_item()
        del item["abstract"]
        result = client._normalise(item, "research_square")
        assert result["abstract"] == ""

    def test_version_from_doi(self):
        client = _make_client()
        item = _make_crossref_item(doi="10.21203/rs.3.rs-1234567/v3")
        result = client._normalise(item, "research_square")
        assert result["version"] == 3

    def test_partial_date_month_only(self):
        client = _make_client()
        item = _make_crossref_item(posted_parts=[[2026, 3]])
        result = client._normalise(item, "research_square")
        assert result["posted_date"] == date(2026, 3, 1)

    def test_partial_date_year_only(self):
        client = _make_client()
        item = _make_crossref_item(posted_parts=[[2026]])
        result = client._normalise(item, "research_square")
        assert result["posted_date"] == date(2026, 1, 1)

    def test_jats_tags_stripped_from_abstract(self):
        client = _make_client()
        item = _make_crossref_item(
            abstract="<jats:p>Clean <jats:italic>abstract</jats:italic>.</jats:p>"
        )
        result = client._normalise(item, "research_square")
        assert result["abstract"] == "Clean abstract."

    def test_corresponding_fields_always_none(self):
        client = _make_client()
        item = _make_crossref_item()
        result = client._normalise(item, "research_square")
        assert result["corresponding_author"] is None
        assert result["corresponding_institution"] is None

    def test_empty_doi_becomes_none(self):
        client = _make_client()
        item = _make_crossref_item()
        item["DOI"] = ""
        result = client._normalise(item, "research_square")
        assert result["doi"] is None


class TestFetch:
    """Tests for CrossrefClient.fetch_papers — HTTP pagination."""

    @respx.mock
    async def test_fetch_single_source_single_page(self):
        items = [_make_crossref_item(doi=f"10.21203/rs.3.rs-{i}/v1") for i in range(3)]
        response = _make_crossref_response(items, total=3)

        respx.get("https://api.crossref.org/works").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.crossref import CrossrefClient

        async with CrossrefClient(
            request_delay=0, sources={"research_square": "10.21203"}
        ) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]

        assert len(papers) == 3
        assert all(p["source_server"] == "research_square" for p in papers)

    @respx.mock
    async def test_fetch_empty_result(self):
        response = _make_crossref_response([], total=0)
        respx.get("https://api.crossref.org/works").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.crossref import CrossrefClient

        async with CrossrefClient(
            request_delay=0, sources={"research_square": "10.21203"}
        ) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 1, 1), date(2026, 1, 1))]

        assert len(papers) == 0

    @respx.mock
    async def test_html_stripped_from_abstract(self):
        item = _make_crossref_item(
            abstract="<jats:p>Clean <jats:italic>abstract</jats:italic>.</jats:p>"
        )
        response = _make_crossref_response([item])
        respx.get("https://api.crossref.org/works").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.crossref import CrossrefClient

        async with CrossrefClient(
            request_delay=0, sources={"research_square": "10.21203"}
        ) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]

        assert papers[0]["abstract"] == "Clean abstract."

    @respx.mock
    async def test_email_sent_as_mailto_param(self):
        response = _make_crossref_response([_make_crossref_item()])
        route = respx.get("https://api.crossref.org/works").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.crossref import CrossrefClient

        async with CrossrefClient(
            email="test@example.com",
            request_delay=0,
            sources={"research_square": "10.21203"},
        ) as client:
            _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]

        assert route.called
        assert "mailto=test%40example.com" in str(route.calls[0].request.url)


class TestRetry:
    """Tests for CrossrefClient retry handling."""

    @respx.mock
    async def test_429_retries_then_succeeds(self):
        items = [_make_crossref_item()]
        ok_response = _make_crossref_response(items)
        route = respx.get("https://api.crossref.org/works").mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=ok_response),
            ]
        )

        from pipeline.ingest.crossref import CrossrefClient

        async with CrossrefClient(
            request_delay=0, sources={"research_square": "10.21203"}
        ) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]
        assert len(papers) == 1
        assert route.call_count == 2

    @respx.mock
    async def test_all_retries_exhausted_skips_source(self):
        """After retries are exhausted, the failing prefix is skipped (not raised)."""
        respx.get("https://api.crossref.org/works").mock(return_value=httpx.Response(429))

        from pipeline.ingest.crossref import CrossrefClient

        async with CrossrefClient(
            request_delay=0, max_retries=2, sources={"research_square": "10.21203"}
        ) as client:
            # Error is caught per-prefix — returns empty list, not an exception
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]
        assert len(papers) == 0
