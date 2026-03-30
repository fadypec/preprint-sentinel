"""Tests for pipeline.db — async session factory with commit/rollback."""

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from pipeline.db import get_session, make_engine
from pipeline.models import Base, Paper, SourceServer


@pytest_asyncio.fixture
async def test_engine():
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
def test_factory(test_engine):
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def test_get_session_commits_on_success(test_factory):
    """Session auto-commits when the block exits normally."""
    async with get_session(factory=test_factory) as session:
        paper = Paper(
            doi="10.1101/commit.test",
            title="Commit test",
            authors=[],
            source_server=SourceServer.BIORXIV,
            posted_date=date(2026, 3, 1),
        )
        session.add(paper)

    # Verify it was committed by reading from a fresh session
    async with test_factory() as verify:
        result = await verify.execute(select(Paper).where(Paper.doi == "10.1101/commit.test"))
        assert result.scalar_one().title == "Commit test"


async def test_get_session_rolls_back_on_error(test_factory):
    """Session rolls back when an exception propagates."""
    with pytest.raises(ValueError, match="deliberate"):
        async with get_session(factory=test_factory) as session:
            paper = Paper(
                doi="10.1101/rollback.test",
                title="Rollback test",
                authors=[],
                source_server=SourceServer.BIORXIV,
                posted_date=date(2026, 3, 1),
            )
            session.add(paper)
            await session.flush()
            raise ValueError("deliberate error")

    # Verify it was NOT committed
    async with test_factory() as verify:
        result = await verify.execute(select(Paper).where(Paper.doi == "10.1101/rollback.test"))
        assert result.scalar_one_or_none() is None


def test_make_engine_returns_engine(monkeypatch):
    """make_engine works when given an explicit URL (no settings needed)."""
    engine = make_engine(url="sqlite+aiosqlite:///:memory:")
    assert engine is not None
    assert "aiosqlite" in str(engine.url)
