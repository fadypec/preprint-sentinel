"""Tests for pipeline.ingest.arxiv — arXiv Atom API client."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_arxiv_atom.xml"


def _make_client():
    from pipeline.ingest.arxiv import ArxivClient

    return ArxivClient(request_delay=0)


class TestParseAtom:
    """Tests for ArxivClient._parse_atom XML parsing."""

    def test_parses_two_entries(self):
        client = _make_client()
        xml_text = FIXTURE_PATH.read_text()
        entries = client._parse_atom(xml_text)
        assert len(entries) == 2

    def test_first_entry_fields(self):
        client = _make_client()
        xml_text = FIXTURE_PATH.read_text()
        entries = client._parse_atom(xml_text)
        assert entries[0]["title"] == "Novel CRISPR-Based Gene Drive in Anopheles Mosquitoes"
        assert entries[0]["authors"] == ["Alice Smith", "Bob Jones"]
        assert entries[0]["doi"] == "10.1234/example.2026"
        assert entries[0]["primary_category"] == "q-bio.GN"
        assert entries[0]["pdf_url"] == "http://arxiv.org/pdf/2026.12345v1"
        assert entries[0]["arxiv_id"] == "2026.12345v1"

    def test_entry_without_doi(self):
        client = _make_client()
        xml_text = FIXTURE_PATH.read_text()
        entries = client._parse_atom(xml_text)
        assert entries[1]["doi"] is None
        assert entries[1]["primary_category"] == "q-bio.BM"

    def test_whitespace_normalised_in_title(self):
        """arXiv titles may contain embedded newlines — verify they're cleaned."""
        client = _make_client()
        xml_text = FIXTURE_PATH.read_text()
        entries = client._parse_atom(xml_text)
        assert "\n" not in entries[0]["title"]

    def test_empty_feed_returns_empty_list(self):
        client = _make_client()
        empty_feed = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom"'
            '      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
            "<opensearch:totalResults>0</opensearch:totalResults>"
            "</feed>"
        )
        entries = client._parse_atom(empty_feed)
        assert entries == []


class TestNormalise:
    """Tests for ArxivClient._normalise field mapping."""

    def test_basic_field_mapping(self):
        client = _make_client()
        entry = {
            "title": "  Test Title  ",
            "summary": "Abstract text here.",
            "authors": ["Alice Smith", "Bob Jones"],
            "published": "2026-03-15T00:00:00Z",
            "doi": "10.1234/example",
            "primary_category": "q-bio.GN",
            "pdf_url": "http://arxiv.org/pdf/2026.12345v1",
            "arxiv_id": "2026.12345v1",
        }
        result = client._normalise(entry)

        assert result["title"] == "Test Title"
        assert result["abstract"] == "Abstract text here."
        assert result["authors"] == [{"name": "Alice Smith"}, {"name": "Bob Jones"}]
        assert result["posted_date"] == date(2026, 3, 15)
        assert result["doi"] == "10.1234/example"
        assert result["source_server"] == "arxiv"
        assert result["subject_category"] == "q-bio.GN"
        assert result["full_text_url"] == "http://arxiv.org/pdf/2026.12345v1"
        assert result["version"] == 1

    def test_no_doi_gives_none(self):
        client = _make_client()
        entry = {
            "title": "Title",
            "summary": "Abstract",
            "authors": ["Author"],
            "published": "2026-03-15T00:00:00Z",
            "doi": None,
            "primary_category": "q-bio.BM",
            "pdf_url": None,
            "arxiv_id": "2026.67890v2",
        }
        result = client._normalise(entry)
        assert result["doi"] is None
        assert result["full_text_url"] is None

    def test_version_extracted_from_arxiv_id(self):
        client = _make_client()
        entry = {
            "title": "Title",
            "summary": "Abstract",
            "authors": ["Author"],
            "published": "2026-03-15T00:00:00Z",
            "doi": None,
            "primary_category": "q-bio.BM",
            "pdf_url": None,
            "arxiv_id": "2026.67890v3",
        }
        result = client._normalise(entry)
        assert result["version"] == 3

    def test_corresponding_fields_always_none(self):
        client = _make_client()
        entry = {
            "title": "T",
            "summary": "A",
            "authors": ["X"],
            "published": "2026-03-15T00:00:00Z",
            "doi": None,
            "primary_category": None,
            "pdf_url": None,
            "arxiv_id": "2026.00001v1",
        }
        result = client._normalise(entry)
        assert result["corresponding_author"] is None
        assert result["corresponding_institution"] is None


class TestFetch:
    """Tests for ArxivClient.fetch_papers — HTTP fetch + pagination."""

    @respx.mock
    async def test_fetch_single_page(self):
        xml_text = FIXTURE_PATH.read_text()
        respx.get("https://export.arxiv.org/api/query").mock(
            return_value=httpx.Response(200, text=xml_text)
        )

        from pipeline.ingest.arxiv import ArxivClient

        async with ArxivClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 15), date(2026, 3, 16))]

        assert len(papers) == 2
        assert papers[0]["source_server"] == "arxiv"
        assert papers[0]["title"] == "Novel CRISPR-Based Gene Drive in Anopheles Mosquitoes"

    @respx.mock
    async def test_fetch_empty_result(self):
        empty_feed = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom"'
            '      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
            "<opensearch:totalResults>0</opensearch:totalResults>"
            "</feed>"
        )
        respx.get("https://export.arxiv.org/api/query").mock(
            return_value=httpx.Response(200, text=empty_feed)
        )

        from pipeline.ingest.arxiv import ArxivClient

        async with ArxivClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 1, 1), date(2026, 1, 1))]

        assert len(papers) == 0


class TestRetry:
    """Tests for ArxivClient retry and error handling."""

    @respx.mock
    async def test_429_retries_then_succeeds(self):
        xml_text = FIXTURE_PATH.read_text()
        route = respx.get("https://export.arxiv.org/api/query").mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, text=xml_text),
            ]
        )
        from pipeline.ingest.arxiv import ArxivClient

        async with ArxivClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 15), date(2026, 3, 16))]
        assert len(papers) == 2
        assert route.call_count == 2

    @respx.mock
    async def test_all_retries_exhausted_raises(self):
        respx.get("https://export.arxiv.org/api/query").mock(return_value=httpx.Response(429))
        from pipeline.ingest.arxiv import ArxivClient

        async with ArxivClient(request_delay=0, max_retries=2) as client:
            with pytest.raises(RuntimeError, match="failed after 2 retries"):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 15), date(2026, 3, 16))]
