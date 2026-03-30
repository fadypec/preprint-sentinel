"""Three-tier deduplication engine.

Tier 1: Exact DOI match (indexed, O(1)).
Tier 2: Fuzzy title + first-author surname within +/-14 days.
Tier 3: For DOI-less papers — title + author + date within +/-7 days.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

import structlog
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.models import (
    DedupRelationship,
    Paper,
    PaperGroup,
)

log = structlog.get_logger()


@dataclass(frozen=True)
class DedupResult:
    """Outcome of a dedup check."""

    is_duplicate: bool
    duplicate_of: uuid.UUID | None
    strategy_used: str  # "doi_match" | "title_author_similarity" | "title_author_date" | "none"
    confidence: float  # 1.0 for DOI match, 0.0-1.0 for fuzzy


def normalise_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for fuzzy comparison."""
    title = title.lower().strip()
    title = re.sub(r"[-/]", " ", title)  # split hyphenated/slashed words before stripping
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def extract_first_author_surname(authors: list[dict]) -> str | None:
    """Extract the surname of the first author from the authors list."""
    if not authors:
        return None
    name = authors[0].get("name", "")
    # Authors are formatted "Surname, I." — take the part before the comma
    parts = name.split(",")
    return parts[0].strip().lower() if parts else None


class DedupEngine:
    """Three-tier deduplication against existing papers in the database."""

    TITLE_SIMILARITY_THRESHOLD = 0.92
    TITLE_SIMILARITY_THRESHOLD_NO_DOI = 0.88
    DATE_WINDOW_DAYS = 14
    DATE_WINDOW_DAYS_NO_DOI = 7

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check(self, paper: dict) -> DedupResult:
        """Run the three-tier dedup cascade. Returns on first match."""
        doi = paper.get("doi")
        title = paper.get("title", "")
        authors = paper.get("authors", [])
        posted_date = paper.get("posted_date", date.today())
        surname = extract_first_author_surname(authors)

        # Tier 1: DOI exact match
        if doi:
            result = await self._check_doi(doi)
            if result is not None:
                return result

        # Tier 2 (DOI papers) or Tier 3 (DOI-less papers): fuzzy title/author
        # DOI papers: stricter threshold (0.92), wider window (14 days)
        # DOI-less papers: relaxed threshold (0.88), tighter window (7 days)
        if surname:
            if doi:
                threshold = self.TITLE_SIMILARITY_THRESHOLD
                window = self.DATE_WINDOW_DAYS
                strategy = "title_author_similarity"
            else:
                threshold = self.TITLE_SIMILARITY_THRESHOLD_NO_DOI
                window = self.DATE_WINDOW_DAYS_NO_DOI
                strategy = "title_author_date"

            match = await self._find_title_author_match(
                title, surname, posted_date, threshold, window
            )
            if match is not None:
                match_id, confidence = match
                return DedupResult(
                    is_duplicate=True,
                    duplicate_of=match_id,
                    strategy_used=strategy,
                    confidence=confidence,
                )

        return DedupResult(
            is_duplicate=False, duplicate_of=None, strategy_used="none", confidence=0.0
        )

    async def _check_doi(self, doi: str) -> DedupResult | None:
        """Tier 1: exact DOI match via indexed lookup."""
        stmt = select(Paper.id).where(Paper.doi == doi).limit(1)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            log.info("dedup_doi_match", doi=doi, canonical_id=str(row))
            return DedupResult(
                is_duplicate=True,
                duplicate_of=row,
                strategy_used="doi_match",
                confidence=1.0,
            )
        return None

    async def _find_title_author_match(
        self,
        title: str,
        first_author_surname: str,
        posted_date: date,
        threshold: float,
        window_days: int,
    ) -> tuple[uuid.UUID, float] | None:
        """Find a matching paper by fuzzy title + author within a date window.

        Returns (matching_paper_id, similarity_score) or None.
        """
        date_from = posted_date - timedelta(days=window_days)
        date_to = posted_date + timedelta(days=window_days)

        stmt = select(Paper.id, Paper.title, Paper.authors).where(
            Paper.posted_date.between(date_from, date_to)
        )
        result = await self._session.execute(stmt)
        candidates = result.all()

        normalised_title = normalise_title(title)

        for cand_id, cand_title, cand_authors in candidates:
            # Check surname match
            cand_surname = extract_first_author_surname(cand_authors or [])
            if cand_surname is None or cand_surname != first_author_surname:
                continue

            # Check title similarity
            cand_normalised = normalise_title(cand_title)
            ratio = fuzz.ratio(normalised_title, cand_normalised) / 100.0

            if ratio >= threshold:
                log.info(
                    "dedup_title_match",
                    candidate_id=str(cand_id),
                    ratio=ratio,
                    threshold=threshold,
                )
                return (cand_id, ratio)

        return None

    async def record_duplicate(
        self,
        canonical_id: uuid.UUID,
        member_id: uuid.UUID,
        result: DedupResult,
        relationship: DedupRelationship = DedupRelationship.DUPLICATE,
    ) -> None:
        """Create a PaperGroup entry and set is_duplicate_of on the member."""
        group = PaperGroup(
            canonical_id=canonical_id,
            member_id=member_id,
            relationship=relationship,
            confidence=result.confidence,
            strategy_used=result.strategy_used,
        )
        self._session.add(group)

        # Update the member paper's FK
        stmt = select(Paper).where(Paper.id == member_id)
        row = await self._session.execute(stmt)
        member_paper = row.scalar_one()
        member_paper.is_duplicate_of = canonical_id

        log.info(
            "dedup_recorded",
            canonical_id=str(canonical_id),
            member_id=str(member_id),
            strategy=result.strategy_used,
        )
