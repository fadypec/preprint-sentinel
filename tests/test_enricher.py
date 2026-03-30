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


class TestEnrichPaper:
    """Tests for enrich_paper function."""

    async def test_all_sources_succeed(self, db_session: AsyncSession):
        from pipeline.enrichment.enricher import enrich_paper

        paper = await insert_paper(
            db_session, title="Test Paper", doi="10.1234/test",
            corresponding_author="Jane Smith",
        )

        mock_settings = MagicMock()
        mock_settings.openalex_email = "test@test.com"
        mock_settings.openalex_request_delay = 0
        mock_settings.semantic_scholar_api_key = MagicMock()
        mock_settings.semantic_scholar_api_key.get_secret_value = MagicMock(return_value="")
        mock_settings.semantic_scholar_request_delay = 0
        mock_settings.orcid_request_delay = 0

        with (
            patch(
                "pipeline.enrichment.enricher.OpenAlexClient"
            ) as mock_oa_cls,
            patch(
                "pipeline.enrichment.enricher.SemanticScholarClient"
            ) as mock_s2_cls,
            patch(
                "pipeline.enrichment.enricher.OrcidClient"
            ) as mock_orcid_cls,
        ):
            # OpenAlex mock
            mock_oa = AsyncMock()
            mock_oa.lookup = AsyncMock(return_value=_openalex_data())
            mock_oa.__aenter__ = AsyncMock(return_value=mock_oa)
            mock_oa.__aexit__ = AsyncMock(return_value=None)
            mock_oa_cls.return_value = mock_oa

            # Semantic Scholar mock
            mock_s2 = AsyncMock()
            mock_s2.lookup = AsyncMock(return_value=_s2_data())
            mock_s2.__aenter__ = AsyncMock(return_value=mock_s2)
            mock_s2.__aexit__ = AsyncMock(return_value=None)
            mock_s2_cls.return_value = mock_s2

            # ORCID mock
            mock_orcid = AsyncMock()
            mock_orcid.lookup = AsyncMock(return_value=_orcid_data())
            mock_orcid.__aenter__ = AsyncMock(return_value=mock_orcid)
            mock_orcid.__aexit__ = AsyncMock(return_value=None)
            mock_orcid_cls.return_value = mock_orcid

            result = await enrich_paper(paper, mock_settings)

        assert result.partial is False
        assert result.sources_succeeded == ["openalex", "semantic_scholar", "orcid"]
        assert result.sources_failed == []
        assert result.data["openalex"]["openalex_work_id"] == "W123"
        assert result.data["s2"]["s2_paper_id"] == "abc123"
        assert result.data["orcid"]["orcid_id"] == "0000-0001-2345-6789"

    async def test_one_source_fails(self, db_session: AsyncSession):
        from pipeline.enrichment.enricher import enrich_paper

        paper = await insert_paper(
            db_session, title="Test Paper", doi="10.1234/test",
            corresponding_author="Jane Smith",
        )

        mock_settings = MagicMock()
        mock_settings.openalex_email = "test@test.com"
        mock_settings.openalex_request_delay = 0
        mock_settings.semantic_scholar_api_key = MagicMock()
        mock_settings.semantic_scholar_api_key.get_secret_value = MagicMock(return_value="")
        mock_settings.semantic_scholar_request_delay = 0
        mock_settings.orcid_request_delay = 0

        with (
            patch(
                "pipeline.enrichment.enricher.OpenAlexClient"
            ) as mock_oa_cls,
            patch(
                "pipeline.enrichment.enricher.SemanticScholarClient"
            ) as mock_s2_cls,
            patch(
                "pipeline.enrichment.enricher.OrcidClient"
            ) as mock_orcid_cls,
        ):
            # OpenAlex succeeds
            mock_oa = AsyncMock()
            mock_oa.lookup = AsyncMock(return_value=_openalex_data())
            mock_oa.__aenter__ = AsyncMock(return_value=mock_oa)
            mock_oa.__aexit__ = AsyncMock(return_value=None)
            mock_oa_cls.return_value = mock_oa

            # Semantic Scholar fails
            mock_s2 = AsyncMock()
            mock_s2.lookup = AsyncMock(side_effect=RuntimeError("API down"))
            mock_s2.__aenter__ = AsyncMock(return_value=mock_s2)
            mock_s2.__aexit__ = AsyncMock(return_value=None)
            mock_s2_cls.return_value = mock_s2

            # ORCID succeeds
            mock_orcid = AsyncMock()
            mock_orcid.lookup = AsyncMock(return_value=_orcid_data())
            mock_orcid.__aenter__ = AsyncMock(return_value=mock_orcid)
            mock_orcid.__aexit__ = AsyncMock(return_value=None)
            mock_orcid_cls.return_value = mock_orcid

            result = await enrich_paper(paper, mock_settings)

        assert result.partial is True
        assert "openalex" in result.sources_succeeded
        assert "orcid" in result.sources_succeeded
        assert result.sources_failed == ["semantic_scholar"]
        assert "openalex" in result.data
        assert "s2" not in result.data
        assert "orcid" in result.data

    async def test_all_sources_fail(self, db_session: AsyncSession):
        from pipeline.enrichment.enricher import enrich_paper

        paper = await insert_paper(
            db_session, title="Test Paper", doi="10.1234/test",
            corresponding_author="Jane Smith",
        )

        mock_settings = MagicMock()
        mock_settings.openalex_email = "test@test.com"
        mock_settings.openalex_request_delay = 0
        mock_settings.semantic_scholar_api_key = MagicMock()
        mock_settings.semantic_scholar_api_key.get_secret_value = MagicMock(return_value="")
        mock_settings.semantic_scholar_request_delay = 0
        mock_settings.orcid_request_delay = 0

        with (
            patch(
                "pipeline.enrichment.enricher.OpenAlexClient"
            ) as mock_oa_cls,
            patch(
                "pipeline.enrichment.enricher.SemanticScholarClient"
            ) as mock_s2_cls,
            patch(
                "pipeline.enrichment.enricher.OrcidClient"
            ) as mock_orcid_cls,
        ):
            for mock_cls in [mock_oa_cls, mock_s2_cls, mock_orcid_cls]:
                mock_inst = AsyncMock()
                mock_inst.lookup = AsyncMock(side_effect=RuntimeError("fail"))
                mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
                mock_inst.__aexit__ = AsyncMock(return_value=None)
                mock_cls.return_value = mock_inst

            result = await enrich_paper(paper, mock_settings)

        assert result.partial is True
        assert result.sources_succeeded == []
        assert set(result.sources_failed) == {"openalex", "semantic_scholar", "orcid"}
        assert result.data == {}

    async def test_orcid_uses_known_orcid_from_openalex(self, db_session: AsyncSession):
        """ORCID client receives known_orcid extracted from OpenAlex data."""
        from pipeline.enrichment.enricher import enrich_paper

        paper = await insert_paper(
            db_session, title="Test Paper", doi="10.1234/test",
            corresponding_author="Jane Smith",
        )

        mock_settings = MagicMock()
        mock_settings.openalex_email = "test@test.com"
        mock_settings.openalex_request_delay = 0
        mock_settings.semantic_scholar_api_key = MagicMock()
        mock_settings.semantic_scholar_api_key.get_secret_value = MagicMock(return_value="")
        mock_settings.semantic_scholar_request_delay = 0
        mock_settings.orcid_request_delay = 0

        with (
            patch(
                "pipeline.enrichment.enricher.OpenAlexClient"
            ) as mock_oa_cls,
            patch(
                "pipeline.enrichment.enricher.SemanticScholarClient"
            ) as mock_s2_cls,
            patch(
                "pipeline.enrichment.enricher.OrcidClient"
            ) as mock_orcid_cls,
        ):
            mock_oa = AsyncMock()
            mock_oa.lookup = AsyncMock(return_value=_openalex_data())
            mock_oa.__aenter__ = AsyncMock(return_value=mock_oa)
            mock_oa.__aexit__ = AsyncMock(return_value=None)
            mock_oa_cls.return_value = mock_oa

            mock_s2 = AsyncMock()
            mock_s2.lookup = AsyncMock(return_value=_s2_data())
            mock_s2.__aenter__ = AsyncMock(return_value=mock_s2)
            mock_s2.__aexit__ = AsyncMock(return_value=None)
            mock_s2_cls.return_value = mock_s2

            mock_orcid = AsyncMock()
            mock_orcid.lookup = AsyncMock(return_value=_orcid_data())
            mock_orcid.__aenter__ = AsyncMock(return_value=mock_orcid)
            mock_orcid.__aexit__ = AsyncMock(return_value=None)
            mock_orcid_cls.return_value = mock_orcid

            await enrich_paper(paper, mock_settings)

        # Verify ORCID was called with the known_orcid from OpenAlex
        mock_orcid.lookup.assert_called_once_with(
            "Jane Smith", known_orcid="0000-0001-2345-6789"
        )
