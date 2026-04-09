"""Tests for pipeline.ingest.zenodo — Zenodo API client."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx


def _make_client(**kwargs):
    from pipeline.ingest.zenodo import ZenodoClient

    return ZenodoClient(request_delay=0, **kwargs)


def _make_zenodo_hit(
    doi: str = "10.5281/zenodo.1234567",
    title: str = "Test Zenodo Preprint",
    creators: list[dict] | None = None,
    description: str = "A test abstract from Zenodo.",
    pub_date: str = "2026-03-15",
    subjects: list[dict] | None = None,
) -> dict:
    """Create a Zenodo record hit matching the real API format."""
    if creators is None:
        creators = [{"name": "Smith, Alice", "orcid": "0000-0001-2345-6789"}]
    hit: dict = {
        "doi": doi,
        "metadata": {
            "title": title,
            "creators": creators,
            "description": description,
            "publication_date": pub_date,
        },
        "links": {
            "html": f"https://zenodo.org/records/{doi.split('.')[-1]}",
        },
    }
    if subjects:
        hit["metadata"]["subjects"] = subjects
    return hit


def _make_zenodo_response(hits: list[dict], total: int | None = None) -> dict:
    """Wrap hits in the Zenodo API response envelope."""
    return {
        "hits": {
            "total": total if total is not None else len(hits),
            "hits": hits,
        },
    }


class TestNormalise:
    """Tests for ZenodoClient._normalise field mapping."""

    def test_basic_field_mapping(self):
        client = _make_client()
        hit = _make_zenodo_hit(
            doi="10.5281/zenodo.9999",
            title="  Zenodo Paper Title  ",
            creators=[
                {"name": "Smith, Alice"},
                {"name": "Jones, Bob"},
            ],
            description="<p>Abstract with <em>HTML</em>.</p>",
            pub_date="2026-03-15",
        )
        result = client._normalise(hit)

        assert result["doi"] == "10.5281/zenodo.9999"
        assert result["title"] == "Zenodo Paper Title"
        assert result["authors"] == [{"name": "Smith, Alice"}, {"name": "Jones, Bob"}]
        assert result["abstract"] == "Abstract with HTML."
        assert result["posted_date"] == date(2026, 3, 15)
        assert result["source_server"] == "zenodo"
        assert result["version"] == 1

    def test_missing_description(self):
        client = _make_client()
        hit = _make_zenodo_hit()
        del hit["metadata"]["description"]
        result = client._normalise(hit)
        assert result["abstract"] == ""

    def test_subject_category(self):
        client = _make_client()
        hit = _make_zenodo_hit(subjects=[{"term": "Molecular Biology"}])
        result = client._normalise(hit)
        assert result["subject_category"] == "Molecular Biology"

    def test_no_subjects_gives_none(self):
        client = _make_client()
        hit = _make_zenodo_hit()
        result = client._normalise(hit)
        assert result["subject_category"] is None

    def test_corresponding_fields_always_none(self):
        client = _make_client()
        hit = _make_zenodo_hit()
        result = client._normalise(hit)
        assert result["corresponding_author"] is None
        assert result["corresponding_institution"] is None

    def test_html_stripped_from_description(self):
        client = _make_client()
        hit = _make_zenodo_hit(description="<p>Some <strong>bold</strong> text.</p>")
        result = client._normalise(hit)
        assert result["abstract"] == "Some bold text."

    def test_no_doi_gives_none(self):
        client = _make_client()
        hit = _make_zenodo_hit()
        del hit["doi"]
        result = client._normalise(hit)
        assert result["doi"] is None


class TestFetch:
    """Tests for ZenodoClient.fetch_papers — HTTP pagination."""

    @respx.mock
    async def test_fetch_single_page(self):
        hits = [_make_zenodo_hit(doi=f"10.5281/zenodo.{i}") for i in range(3)]
        response = _make_zenodo_response(hits)
        respx.get("https://zenodo.org/api/records").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.zenodo import ZenodoClient

        async with ZenodoClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]

        assert len(papers) == 3
        assert all(p["source_server"] == "zenodo" for p in papers)

    @respx.mock
    async def test_fetch_empty(self):
        response = _make_zenodo_response([], total=0)
        respx.get("https://zenodo.org/api/records").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.zenodo import ZenodoClient

        async with ZenodoClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 1, 1), date(2026, 1, 1))]

        assert len(papers) == 0

    @respx.mock
    async def test_query_params_correct(self):
        response = _make_zenodo_response([_make_zenodo_hit()])
        route = respx.get("https://zenodo.org/api/records").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.zenodo import ZenodoClient

        async with ZenodoClient(request_delay=0) as client:
            _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]

        assert route.called
        url_str = str(route.calls[0].request.url)
        assert "type=publication" in url_str
        assert "subtype=preprint" in url_str


class TestRetry:
    """Tests for ZenodoClient retry handling."""

    @respx.mock
    async def test_503_retries_then_succeeds(self):
        hits = [_make_zenodo_hit()]
        ok_response = _make_zenodo_response(hits)
        route = respx.get("https://zenodo.org/api/records").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json=ok_response),
            ]
        )

        from pipeline.ingest.zenodo import ZenodoClient

        async with ZenodoClient(request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]
        assert len(papers) == 1
        assert route.call_count == 2

    @respx.mock
    async def test_all_retries_exhausted_raises(self):
        respx.get("https://zenodo.org/api/records").mock(return_value=httpx.Response(429))

        from pipeline.ingest.zenodo import ZenodoClient

        async with ZenodoClient(request_delay=0, max_retries=2) as client:
            with pytest.raises(RuntimeError, match="failed after 2 retries"):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]
