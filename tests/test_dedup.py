"""Tests for pipeline.ingest.dedup — three-tier deduplication engine."""

from __future__ import annotations

from datetime import date

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


class TestTitleAuthorSimilarity:
    """Tier 2: fuzzy title + first-author surname match."""

    async def test_similar_title_same_author(self, db_session):
        """Nearly identical title + same first author surname = duplicate."""
        from pipeline.ingest.dedup import DedupEngine

        existing = await insert_paper(
            db_session,
            doi="10.1101/existing.001",
            title="Novel CRISPR approach to gene editing in primary T cells",
            authors=[{"name": "Smith, J."}, {"name": "Jones, A."}],
            posted_date=date(2026, 3, 10),
        )

        engine = DedupEngine(db_session)
        result = await engine.check({
            "doi": "10.1101/different.002",
            "title": "A novel CRISPR approach to gene editing in primary T cells",
            "authors": [{"name": "Smith, J."}],
            "posted_date": date(2026, 3, 12),
        })

        assert result.is_duplicate is True
        assert result.duplicate_of == existing.id
        assert result.strategy_used == "title_author_similarity"
        assert result.confidence > 0.92

    async def test_title_below_threshold(self, db_session):
        """Title similarity below 0.92 threshold — not a duplicate."""
        from pipeline.ingest.dedup import DedupEngine

        await insert_paper(
            db_session,
            doi="10.1101/existing.001",
            title="Novel CRISPR approach to gene editing in primary T cells",
            authors=[{"name": "Smith, J."}],
            posted_date=date(2026, 3, 10),
        )

        engine = DedupEngine(db_session)
        result = await engine.check({
            "doi": "10.1101/different.003",
            "title": "Traditional methods for gene therapy using viral vectors",
            "authors": [{"name": "Smith, J."}],
            "posted_date": date(2026, 3, 12),
        })

        assert result.is_duplicate is False

    async def test_same_title_different_author(self, db_session):
        """Same title but different first author — not a duplicate."""
        from pipeline.ingest.dedup import DedupEngine

        await insert_paper(
            db_session,
            doi="10.1101/existing.001",
            title="Population dynamics in temperate forests",
            authors=[{"name": "Smith, J."}],
            posted_date=date(2026, 3, 10),
        )

        engine = DedupEngine(db_session)
        result = await engine.check({
            "doi": "10.1101/different.004",
            "title": "Population dynamics in temperate forests",
            "authors": [{"name": "Johnson, K."}],
            "posted_date": date(2026, 3, 12),
        })

        assert result.is_duplicate is False

    async def test_date_window_respected(self, db_session):
        """Matching title/author but outside +/-14 day window — not duplicate."""
        from pipeline.ingest.dedup import DedupEngine

        await insert_paper(
            db_session,
            doi="10.1101/existing.001",
            title="Novel CRISPR approach to gene editing",
            authors=[{"name": "Smith, J."}],
            posted_date=date(2026, 1, 1),
        )

        engine = DedupEngine(db_session)
        result = await engine.check({
            "doi": "10.1101/different.005",
            "title": "Novel CRISPR approach to gene editing",
            "authors": [{"name": "Smith, J."}],
            "posted_date": date(2026, 6, 1),  # 5 months later
        })

        assert result.is_duplicate is False
