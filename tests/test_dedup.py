"""Tests for pipeline.ingest.dedup — three-tier deduplication engine."""

from __future__ import annotations

from datetime import date

import pytest

from pipeline.models import Paper, PaperGroup, SourceServer
from tests.conftest import insert_paper


class TestDoiMatch:
    """Tier 1: exact DOI match."""

    async def test_doi_exact_match(self, db_session):
        """Paper with matching DOI is identified as duplicate."""
        from pipeline.ingest.dedup import DedupEngine

        existing = await insert_paper(
            db_session,
            doi="10.1101/2026.03.01.123456",
            title="Original Paper",
        )

        engine = DedupEngine(db_session)
        result = await engine.check({
            "doi": "10.1101/2026.03.01.123456",
            "title": "Original Paper (repost)",
            "authors": [{"name": "Smith, J."}],
            "posted_date": date(2026, 3, 1),
        })

        assert result.is_duplicate is True
        assert result.duplicate_of == existing.id
        assert result.strategy_used == "doi_match"
        assert result.confidence == 1.0

    async def test_no_doi_match(self, db_session):
        """Paper with a different DOI is not flagged as duplicate."""
        from pipeline.ingest.dedup import DedupEngine

        await insert_paper(db_session, doi="10.1101/2026.03.01.111111")

        engine = DedupEngine(db_session)
        result = await engine.check({
            "doi": "10.1101/2026.03.01.999999",
            "title": "Completely Different Paper",
            "authors": [{"name": "Other, A."}],
            "posted_date": date(2026, 3, 1),
        })

        assert result.is_duplicate is False
        assert result.duplicate_of is None
        assert result.strategy_used == "none"

    async def test_no_doi_skips_to_next_tier(self, db_session):
        """Paper with no DOI skips tier 1 (no crash, no false match)."""
        from pipeline.ingest.dedup import DedupEngine

        await insert_paper(db_session, doi="10.1101/2026.03.01.111111")

        engine = DedupEngine(db_session)
        result = await engine.check({
            "doi": None,
            "title": "Totally Unrelated Paper",
            "authors": [{"name": "Nobody, X."}],
            "posted_date": date(2026, 3, 1),
        })

        assert result.is_duplicate is False
