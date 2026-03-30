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
            abstract="The 1.8 &Aring; structure of ACE2 shows &lt;50% occupancy &amp; high B-factors."
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
        assert result["full_text_url"] == "https://www.biorxiv.org/content/10.1101/2026.03.15.500001v1.source.xml"

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
