"""Shared test fixtures and factory helpers."""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from pipeline.models import Base, Paper, SourceServer

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_engine():
    """Create an in-memory SQLite async engine with all tables."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    """Yield a clean async session. Does NOT auto-commit — tests manage their own state."""
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Record factories
# ---------------------------------------------------------------------------


def make_raw_record(
    doi: str = "10.1101/2026.03.01.123456",
    title: str = "Test Paper Title",
    authors: str = "Smith, J.; Jones, A.",
    author_corresponding: str = "John Smith",
    author_corresponding_institution: str = "MIT",
    date_str: str = "2026-03-01",
    version: str = "1",
    category: str = "microbiology",
    abstract: str = "We describe a novel approach to studying pathogen dynamics.",
    published: str = "NA",
    server: str = "biorxiv",
    jatsxml: str | None = None,
) -> dict:
    """Create a raw record matching the CSHL bioRxiv/medRxiv API format."""
    record = {
        "doi": doi,
        "title": title,
        "authors": authors,
        "author_corresponding": author_corresponding,
        "author_corresponding_institution": author_corresponding_institution,
        "date": date_str,
        "version": version,
        "category": category,
        "abstract": abstract,
        "published": published,
        "server": server,
    }
    if jatsxml is not None:
        record["jatsxml"] = jatsxml
    return record


def make_api_response(collection: list[dict], total: int | None = None) -> dict:
    """Wrap raw records in the CSHL API response envelope."""
    if total is None:
        total = len(collection)
    return {
        "messages": [{"status": "ok", "count": len(collection), "total": total}],
        "collection": collection,
    }


def make_collection(n: int, start_idx: int = 0, server: str = "biorxiv") -> list[dict]:
    """Generate n raw records with unique DOIs."""
    return [
        make_raw_record(
            doi=f"10.1101/2026.03.01.{100000 + start_idx + i}",
            title=f"Generated Paper {start_idx + i}",
            authors=f"Author{start_idx + i}, A.; Coauthor, B.",
            server=server,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Europe PMC record factories
# ---------------------------------------------------------------------------


def make_europepmc_record(
    ppr_id: str = "PPR100001",
    doi: str | None = "10.1101/2026.03.01.123456",
    title: str = "Test Europe PMC Paper",
    author_string: str = "Smith J, Jones A",
    first_pub_date: str = "2026-03-01",
    abstract: str = "A test abstract from Europe PMC.",
    source: str = "PPR",
) -> dict:
    """Create a raw record matching the Europe PMC search API format."""
    record: dict = {
        "id": ppr_id,
        "title": title,
        "authorString": author_string,
        "firstPublicationDate": first_pub_date,
        "abstractText": abstract,
        "source": source,
    }
    if doi is not None:
        record["doi"] = doi
    return record


def make_europepmc_response(
    results: list[dict],
    hit_count: int | None = None,
    next_cursor: str = "AoE_next",
) -> dict:
    """Wrap Europe PMC records in the API response envelope."""
    if hit_count is None:
        hit_count = len(results)
    return {
        "hitCount": hit_count,
        "nextCursorMark": next_cursor,
        "resultList": {"result": results},
    }


async def insert_paper(session: AsyncSession, **kwargs) -> Paper:
    """Insert a Paper into the test database and return it (flushed, with ID)."""
    defaults: dict = {
        "doi": f"10.1101/2026.03.01.{uuid.uuid4().hex[:6]}",
        "title": "Default Test Paper",
        "authors": [{"name": "Smith, J."}],
        "source_server": SourceServer.BIORXIV,
        "posted_date": date(2026, 3, 1),
        "abstract": "Default test abstract.",
    }
    defaults.update(kwargs)
    paper = Paper(**defaults)
    session.add(paper)
    await session.flush()
    return paper


# ---------------------------------------------------------------------------
# Fixture data loader
# ---------------------------------------------------------------------------


def load_fixture(name: str) -> dict | list:
    """Load a JSON fixture file by name."""
    path = FIXTURES_DIR / name
    return json.loads(path.read_text())
