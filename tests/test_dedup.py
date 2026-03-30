"""Tests for pipeline.ingest.dedup — three-tier deduplication engine."""

from __future__ import annotations

from datetime import date

from pipeline.models import PaperGroup
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


class TestDoiLessFallback:
    """Tier 3: DOI-less papers use tighter date window + lower threshold."""

    async def test_doi_less_fallback_matches(self, db_session):
        """Paper without DOI matches existing paper via title/author/date."""
        from pipeline.ingest.dedup import DedupEngine

        existing = await insert_paper(
            db_session,
            doi=None,
            title="Novel findings on bat coronavirus ecology in Vietnamese caves",
            authors=[{"name": "Tran, V."}],
            posted_date=date(2026, 3, 1),
        )

        engine = DedupEngine(db_session)
        result = await engine.check({
            "doi": None,
            "title": "Novel findings in bat coronavirus ecology in Vietnamese caves",
            "authors": [{"name": "Tran, V."}],
            "posted_date": date(2026, 3, 3),  # within 7-day window
        })

        assert result.is_duplicate is True
        assert result.duplicate_of == existing.id
        assert result.strategy_used == "title_author_date"

    async def test_doi_less_outside_7_day_window(self, db_session):
        """DOI-less paper outside +/-7 day window is not matched at tier 3."""
        from pipeline.ingest.dedup import DedupEngine

        await insert_paper(
            db_session,
            doi=None,
            title="Novel findings in bat coronavirus ecology",
            authors=[{"name": "Tran, V."}],
            posted_date=date(2026, 3, 1),
        )

        engine = DedupEngine(db_session)
        result = await engine.check({
            "doi": None,
            "title": "Novel findings in bat coronavirus ecology",
            "authors": [{"name": "Tran, V."}],
            "posted_date": date(2026, 3, 20),  # outside 7-day window
        })

        assert result.is_duplicate is False


class TestRecordDuplicate:
    """Recording duplicates in PaperGroup."""

    async def test_record_creates_paper_group(self, db_session):
        """record_duplicate creates a PaperGroup row with correct fields."""
        from pipeline.ingest.dedup import DedupEngine, DedupResult

        p1 = await insert_paper(db_session, doi="10.1101/canonical")
        p2 = await insert_paper(db_session, doi="10.1101/duplicate")

        engine = DedupEngine(db_session)
        dedup_result = DedupResult(
            is_duplicate=True,
            duplicate_of=p1.id,
            strategy_used="doi_match",
            confidence=1.0,
        )
        await engine.record_duplicate(p1.id, p2.id, dedup_result)
        await db_session.flush()

        from sqlalchemy import select
        stmt = select(PaperGroup).where(PaperGroup.canonical_id == p1.id)
        result = await db_session.execute(stmt)
        group = result.scalar_one()

        assert group.member_id == p2.id
        assert group.strategy_used == "doi_match"
        assert group.confidence == 1.0

    async def test_record_sets_is_duplicate_of(self, db_session):
        """record_duplicate updates the member paper's is_duplicate_of FK."""
        from pipeline.ingest.dedup import DedupEngine, DedupResult

        p1 = await insert_paper(db_session, doi="10.1101/canonical.2")
        p2 = await insert_paper(db_session, doi="10.1101/duplicate.2")

        engine = DedupEngine(db_session)
        dedup_result = DedupResult(
            is_duplicate=True,
            duplicate_of=p1.id,
            strategy_used="doi_match",
            confidence=1.0,
        )
        await engine.record_duplicate(p1.id, p2.id, dedup_result)
        await db_session.flush()

        # Re-fetch paper to verify FK was set
        from sqlalchemy import select

        from pipeline.models import Paper

        stmt = select(Paper).where(Paper.id == p2.id)
        result = await db_session.execute(stmt)
        updated = result.scalar_one()
        assert updated.is_duplicate_of == p1.id
