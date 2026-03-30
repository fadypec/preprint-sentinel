"""Async database engine and session factory.

Usage:
    async with get_session() as session:
        result = await session.execute(select(Paper))

For tests, pass a custom factory:
    factory = async_sessionmaker(test_engine, ...)
    async with get_session(factory=factory) as session:
        ...
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pipeline.config import get_settings


def make_engine(url: str | None = None):
    """Create an async SQLAlchemy engine.

    Args:
        url: Database URL. If None, reads from Settings.
    """
    if url is None:
        url = get_settings().database_url
    # SQLite does not support connection pool sizing parameters.
    if url.startswith("sqlite"):
        return create_async_engine(url)
    return create_async_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


def make_session_factory(engine=None) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given engine."""
    if engine is None:
        engine = make_engine()
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_session(
    factory: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncIterator[AsyncSession]:
    """Yield a database session with auto-commit on success, rollback on error."""
    if factory is None:
        factory = make_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
