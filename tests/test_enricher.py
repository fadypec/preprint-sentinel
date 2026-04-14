"""Tests for pipeline.enrichment.enricher -- orchestrates all enrichment sources."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import insert_paper


def _openalex_data() -> dict:
    return {
        "openalex_work_id": "W123",
        "cited_by_count": 42,
        "topics": [{"name": "Virology", "score": 0.95}],
        "authors": [
            {
                "name": "Jane Smith",
                "openalex_id": "A111",
                "orcid": "0000-0001-2345-6789",
                "institution": "MIT",
                "institution_country": "US",
                "institution_type": "education",
                "works_count": 150,
                "cited_by_count": 3200,
            }
        ],
        "primary_institution": "MIT",
        "primary_institution_country": "US",
        "funder_names": ["NIH"],
    }


def _s2_data() -> dict:
    return {
        "s2_paper_id": "abc123",
        "tldr": "A paper about H5N1.",
        "citation_count": 15,
        "influential_citation_count": 3,
        "first_author_h_index": 25,
        "first_author_paper_count": 80,
        "first_author_citation_count": 4500,
    }


def _orcid_data() -> dict:
    return {
        "orcid_id": "0000-0001-2345-6789",
        "current_institution": "MIT",
        "employment_history": ["MIT (2020-present)"],
        "education": ["PhD, Harvard (2015)"],
    }


def _crossref_data() -> dict:
    return {
        "funders": [
            {
                "name": "National Institutes of Health",
                "doi": "10.13039/100000002",
                "award": ["R01AI123456"],
            },
        ],
    }


def _mock_settings() -> MagicMock:
    """Create a mock settings object with all required enrichment fields."""
    s = MagicMock()
    s.openalex_email = "test@test.com"
    s.openalex_request_delay = 0
    s.semantic_scholar_api_key = MagicMock()
    s.semantic_scholar_api_key.get_secret_value = MagicMock(return_value="")
    s.semantic_scholar_request_delay = 0
    s.orcid_request_delay = 0
    s.crossref_email = "test@test.com"
    s.crossref_request_delay = 0
    return s


def _make_async_client_mock(lookup_return=None, lookup_side_effect=None):
    """Create a mock async context manager client with a .lookup() method."""
    mock = AsyncMock()
    if lookup_side_effect:
        mock.lookup = AsyncMock(side_effect=lookup_side_effect)
    else:
        mock.lookup = AsyncMock(return_value=lookup_return)
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    return mock


# All four enrichment source class paths
_ENRICHMENT_PATCHES = (
    "pipeline.enrichment.enricher.OpenAlexClient",
    "pipeline.enrichment.enricher.SemanticScholarClient",
    "pipeline.enrichment.enricher.OrcidClient",
    "pipeline.enrichment.enricher.CrossrefEnrichmentClient",
)


class TestEnrichPaper:
    """Tests for enrich_paper function."""

    async def test_all_sources_succeed(self, db_session: AsyncSession):
        from pipeline.enrichment.enricher import enrich_paper

        paper = await insert_paper(
            db_session, title="Test Paper", doi="10.1234/test",
            corresponding_author="Jane Smith",
        )

        with patch(_ENRICHMENT_PATCHES[0]) as oa_cls, \
             patch(_ENRICHMENT_PATCHES[1]) as s2_cls, \
             patch(_ENRICHMENT_PATCHES[2]) as orcid_cls, \
             patch(_ENRICHMENT_PATCHES[3]) as cr_cls:
            oa_cls.return_value = _make_async_client_mock(_openalex_data())
            s2_cls.return_value = _make_async_client_mock(_s2_data())
            orcid_cls.return_value = _make_async_client_mock(_orcid_data())
            cr_cls.return_value = _make_async_client_mock(_crossref_data())

            result = await enrich_paper(paper, _mock_settings())

        assert result.partial is False
        assert "openalex" in result.sources_succeeded
        assert "semantic_scholar" in result.sources_succeeded
        assert "orcid" in result.sources_succeeded
        assert "crossref" in result.sources_succeeded
        assert result.sources_failed == []
        assert result.data["openalex"]["openalex_work_id"] == "W123"
        assert result.data["s2"]["s2_paper_id"] == "abc123"
        assert result.data["orcid"]["orcid_id"] == "0000-0001-2345-6789"
        assert result.data["crossref"]["funders"][0]["name"] == "National Institutes of Health"

    async def test_one_source_fails(self, db_session: AsyncSession):
        from pipeline.enrichment.enricher import enrich_paper

        paper = await insert_paper(
            db_session, title="Test Paper", doi="10.1234/test",
            corresponding_author="Jane Smith",
        )

        with patch(_ENRICHMENT_PATCHES[0]) as oa_cls, \
             patch(_ENRICHMENT_PATCHES[1]) as s2_cls, \
             patch(_ENRICHMENT_PATCHES[2]) as orcid_cls, \
             patch(_ENRICHMENT_PATCHES[3]) as cr_cls:
            oa_cls.return_value = _make_async_client_mock(_openalex_data())
            s2_cls.return_value = _make_async_client_mock(
                lookup_side_effect=RuntimeError("API down"),
            )
            orcid_cls.return_value = _make_async_client_mock(_orcid_data())
            cr_cls.return_value = _make_async_client_mock(_crossref_data())

            result = await enrich_paper(paper, _mock_settings())

        assert result.partial is True
        assert "openalex" in result.sources_succeeded
        assert "orcid" in result.sources_succeeded
        assert "crossref" in result.sources_succeeded
        assert result.sources_failed == ["semantic_scholar"]
        assert "s2" not in result.data

    async def test_all_sources_fail(self, db_session: AsyncSession):
        from pipeline.enrichment.enricher import enrich_paper

        paper = await insert_paper(
            db_session, title="Test Paper", doi="10.1234/test",
            corresponding_author="Jane Smith",
        )

        with patch(_ENRICHMENT_PATCHES[0]) as oa_cls, \
             patch(_ENRICHMENT_PATCHES[1]) as s2_cls, \
             patch(_ENRICHMENT_PATCHES[2]) as orcid_cls, \
             patch(_ENRICHMENT_PATCHES[3]) as cr_cls:
            for cls in [oa_cls, s2_cls, orcid_cls, cr_cls]:
                cls.return_value = _make_async_client_mock(lookup_side_effect=RuntimeError("fail"))

            result = await enrich_paper(paper, _mock_settings())

        assert result.partial is True
        assert result.sources_succeeded == []
        assert set(result.sources_failed) == {"openalex", "semantic_scholar", "orcid", "crossref"}
        assert result.data == {}

    async def test_orcid_uses_known_orcid_from_openalex(self, db_session: AsyncSession):
        """ORCID client receives known_orcid extracted from OpenAlex data."""
        from pipeline.enrichment.enricher import enrich_paper

        paper = await insert_paper(
            db_session, title="Test Paper", doi="10.1234/test",
            corresponding_author="Jane Smith",
        )

        with patch(_ENRICHMENT_PATCHES[0]) as oa_cls, \
             patch(_ENRICHMENT_PATCHES[1]) as s2_cls, \
             patch(_ENRICHMENT_PATCHES[2]) as orcid_cls, \
             patch(_ENRICHMENT_PATCHES[3]) as cr_cls:
            oa_cls.return_value = _make_async_client_mock(_openalex_data())
            s2_cls.return_value = _make_async_client_mock(_s2_data())
            mock_orcid = _make_async_client_mock(_orcid_data())
            orcid_cls.return_value = mock_orcid
            cr_cls.return_value = _make_async_client_mock(_crossref_data())

            await enrich_paper(paper, _mock_settings())

        # Verify ORCID was called with the known_orcid from OpenAlex
        mock_orcid.lookup.assert_called_once_with("Jane Smith", known_orcid="0000-0001-2345-6789")
