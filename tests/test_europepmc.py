"""Tests for pipeline.ingest.europepmc — Europe PMC API client."""

from __future__ import annotations

from datetime import date

from tests.conftest import make_europepmc_record


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
