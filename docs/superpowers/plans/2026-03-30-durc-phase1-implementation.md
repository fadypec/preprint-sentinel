# Phase 1 Implementation Plan: Core Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational pipeline scaffold — project packaging, database models, bioRxiv/medRxiv ingest client with pagination and retry, and the three-tier deduplication engine.

**Architecture:** A Python async pipeline reads from the CSHL bioRxiv/medRxiv REST API, normalises metadata to a common schema, deduplicates via DOI/title/author matching, and persists to PostgreSQL. All database access is async (SQLAlchemy 2.0 + asyncpg). Tests run against in-memory SQLite.

**Tech Stack:** Python 3.11+, uv + hatchling, SQLAlchemy 2.0 async, asyncpg, httpx, structlog, pydantic-settings, rapidfuzz, pytest + pytest-asyncio + respx, Alembic, Docker Compose (PostgreSQL 16).

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `pyproject.toml` | Package metadata, dependencies, tool config |
| Create | `docker-compose.yml` | Local PostgreSQL 16 container |
| Create | `.env.example` | Documented env var template |
| Create | `.gitignore` | Python + env + IDE ignores |
| Create | `pipeline/__init__.py` | Package marker |
| Create | `pipeline/config.py` | Typed settings via pydantic-settings |
| Create | `pipeline/logging.py` | structlog JSON configuration |
| Create | `pipeline/models.py` | SQLAlchemy ORM models: Paper, PaperGroup, AssessmentLog |
| Create | `pipeline/db.py` | Async engine + session factory |
| Create | `pipeline/ingest/__init__.py` | Package marker |
| Create | `pipeline/ingest/biorxiv.py` | bioRxiv/medRxiv API client |
| Create | `pipeline/ingest/dedup.py` | Three-tier deduplication engine |
| Create | `tests/__init__.py` | Package marker |
| Create | `tests/conftest.py` | Shared fixtures: db_session, record factories |
| Create | `tests/test_config.py` | Config loading + secret redaction tests |
| Create | `tests/test_models.py` | Model creation + CRUD tests |
| Create | `tests/test_ingest.py` | bioRxiv client: normalise, fetch, pagination, retry |
| Create | `tests/test_dedup.py` | Dedup: DOI match, fuzzy, DOI-less, recording |
| Create | `tests/fixtures/sample_biorxiv.json` | 10 realistic CSHL API records |
| Create | `alembic.ini` | Alembic config |
| Create | `alembic/env.py` | Async migration runner |
| Create | `alembic/script.py.mako` | Migration template |
| Create | `alembic/versions/` | Migration scripts directory |

---

## Task 1: Project Scaffold & Git Init

**Files:**
- Create: `pyproject.toml`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `pipeline/__init__.py`
- Create: `pipeline/ingest/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/fixtures/` (directory)

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "durc-triage"
version = "0.1.0"
description = "AI-enabled pipeline for triaging dual-use research of concern in preprints"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",
    "httpx>=0.27.0",
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "structlog>=24.0.0",
    "pydantic-settings>=2.4.0",
    "python-dotenv>=1.0.0",
    "rapidfuzz>=3.9.0",
    "lxml>=5.2.0",
    "apscheduler>=3.10.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "aiosqlite>=0.20.0",
    "respx>=0.22.0",
    "ruff>=0.7.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP"]
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: durc
      POSTGRES_PASSWORD: durc_local
      POSTGRES_DB: durc_triage
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U durc"]
      interval: 5s
      retries: 3

volumes:
  pgdata:
```

- [ ] **Step 3: Create `.env.example`**

```bash
# === Database ===
# For local dev with docker-compose:
DATABASE_URL=postgresql+asyncpg://durc:durc_local@localhost:5432/durc_triage

# === Anthropic ===
ANTHROPIC_API_KEY=sk-ant-REPLACE_ME

# === External APIs (all free, register for keys) ===
NCBI_API_KEY=
UNPAYWALL_EMAIL=
OPENALEX_EMAIL=

# === Pipeline tuning ===
DAILY_RUN_HOUR=6
COARSE_FILTER_THRESHOLD=0.8
BIORXIV_REQUEST_DELAY=1.0
```

- [ ] **Step 4: Create `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.eggs/

# Environment
.env
.venv/
venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/

# uv
uv.lock

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 5: Create package markers**

Create these empty files:
- `pipeline/__init__.py`
- `pipeline/ingest/__init__.py`
- `tests/__init__.py`

- [ ] **Step 6: Create fixtures directory**

```bash
mkdir -p tests/fixtures
```

- [ ] **Step 7: Install dependencies**

```bash
uv sync --all-extras
```

Expected: resolves all dependencies, creates `.venv/` and `uv.lock`.

- [ ] **Step 8: Git init and initial commit**

```bash
git init
git add pyproject.toml docker-compose.yml .env.example .gitignore pipeline/ tests/ uv.lock
git commit -m "feat: project scaffold with dependencies and docker-compose"
```

---

## Task 2: Configuration & Logging

**Files:**
- Create: `pipeline/config.py`
- Create: `pipeline/logging.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test for config**

Create `tests/test_config.py`:

```python
"""Tests for pipeline.config — typed settings from env vars."""

import os

from pydantic import SecretStr


def test_settings_loads_from_env(monkeypatch):
    """Settings reads DATABASE_URL and ANTHROPIC_API_KEY from env."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

    # Force fresh import (pydantic-settings reads env at instantiation time)
    from pipeline.config import Settings

    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@localhost/test"
    assert s.anthropic_api_key.get_secret_value() == "sk-ant-test-key-12345"


def test_settings_defaults(monkeypatch):
    """Optional fields have sensible defaults."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-key")

    from pipeline.config import Settings

    s = Settings()
    assert s.stage1_model == "claude-haiku-4-5-20251001"
    assert s.coarse_filter_threshold == 0.8
    assert s.daily_run_hour == 6
    assert s.biorxiv_request_delay == 1.0
    assert s.ncbi_api_key == ""


def test_secret_str_redacts_in_repr(monkeypatch):
    """SecretStr must never leak in repr/str (logs, tracebacks)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-super-secret")

    from pipeline.config import Settings

    s = Settings()
    assert "sk-ant-super-secret" not in repr(s)
    assert "sk-ant-super-secret" not in str(s.anthropic_api_key)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'pipeline.config'`

- [ ] **Step 3: Implement `pipeline/config.py`**

```python
"""Typed configuration loaded from environment variables.

All API keys use SecretStr so they are never logged or printed in tracebacks.
Instantiate via get_settings() for a cached singleton.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Database
    database_url: str

    # Anthropic
    anthropic_api_key: SecretStr

    # External APIs (free, email-based auth)
    ncbi_api_key: str = ""
    unpaywall_email: str = ""
    openalex_email: str = ""
    semantic_scholar_api_key: SecretStr = SecretStr("")

    # Model selection
    stage1_model: str = "claude-haiku-4-5-20251001"
    stage2_model: str = "claude-sonnet-4-6"
    stage3_model: str = "claude-opus-4-6"

    # Pipeline tuning
    coarse_filter_threshold: float = 0.8
    daily_run_hour: int = 6

    # Rate limits (seconds between requests)
    biorxiv_request_delay: float = 1.0
    pubmed_request_delay: float = 0.1


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Implement `pipeline/logging.py`**

```python
"""Structured JSON logging via structlog.

Import this module once at application startup to configure logging.
All subsequent structlog.get_logger() calls will use these settings.
"""

import logging

import structlog


def configure_logging(level: int = logging.INFO) -> None:
    """Configure structlog for JSON output with context vars."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/config.py pipeline/logging.py tests/test_config.py
git commit -m "feat: add typed config with SecretStr and structlog logging setup"
```

---

## Task 3: Database Models

**Files:**
- Create: `pipeline/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
"""Tests for pipeline.models — SQLAlchemy ORM models."""

import uuid
from datetime import date, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def model_session():
    """Yield an async session backed by in-memory SQLite."""
    from pipeline.models import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


async def test_create_all_succeeds(model_session: AsyncSession):
    """Base.metadata.create_all works without errors on SQLite."""
    # If we got here, create_all in the fixture succeeded
    result = await model_session.execute(select(1))
    assert result.scalar() == 1


async def test_paper_insert_and_read(model_session: AsyncSession):
    """Insert a Paper row and read it back with correct field types."""
    from pipeline.models import Paper, PipelineStage, ReviewStatus, SourceServer

    paper = Paper(
        doi="10.1101/2026.03.01.123456",
        title="Gain-of-function analysis of H5N1 transmissibility",
        authors=[{"name": "Smith, J."}, {"name": "Jones, A."}],
        source_server=SourceServer.BIORXIV,
        posted_date=date(2026, 3, 1),
        abstract="We describe experiments enhancing airborne transmissibility...",
        subject_category="microbiology",
    )
    model_session.add(paper)
    await model_session.flush()

    result = await model_session.execute(select(Paper).where(Paper.doi == "10.1101/2026.03.01.123456"))
    row = result.scalar_one()

    assert isinstance(row.id, uuid.UUID)
    assert row.title == "Gain-of-function analysis of H5N1 transmissibility"
    assert row.authors == [{"name": "Smith, J."}, {"name": "Jones, A."}]
    assert row.source_server == SourceServer.BIORXIV
    assert row.posted_date == date(2026, 3, 1)
    assert row.pipeline_stage == PipelineStage.INGESTED
    assert row.review_status == ReviewStatus.UNREVIEWED
    assert row.is_duplicate_of is None


async def test_paper_group_insert(model_session: AsyncSession):
    """Insert a PaperGroup linking two papers."""
    from pipeline.models import DedupRelationship, Paper, PaperGroup, SourceServer

    p1 = Paper(
        doi="10.1101/2026.03.01.111111",
        title="Paper A",
        authors=[{"name": "A, B."}],
        source_server=SourceServer.BIORXIV,
        posted_date=date(2026, 3, 1),
    )
    p2 = Paper(
        doi="10.1101/2026.03.01.111111",
        title="Paper A (duplicate)",
        authors=[{"name": "A, B."}],
        source_server=SourceServer.EUROPEPMC,
        posted_date=date(2026, 3, 1),
        is_duplicate_of=p1.id,
    )
    model_session.add_all([p1, p2])
    await model_session.flush()

    group = PaperGroup(
        canonical_id=p1.id,
        member_id=p2.id,
        relationship=DedupRelationship.DUPLICATE,
        confidence=1.0,
        strategy_used="doi_match",
    )
    model_session.add(group)
    await model_session.flush()

    result = await model_session.execute(
        select(PaperGroup).where(PaperGroup.canonical_id == p1.id)
    )
    row = result.scalar_one()
    assert row.member_id == p2.id
    assert row.relationship == DedupRelationship.DUPLICATE
    assert row.strategy_used == "doi_match"


async def test_assessment_log_insert(model_session: AsyncSession):
    """Insert an AssessmentLog entry and verify all fields persist."""
    from pipeline.models import AssessmentLog, Paper, SourceServer

    paper = Paper(
        doi="10.1101/2026.03.01.999999",
        title="Test paper",
        authors=[],
        source_server=SourceServer.BIORXIV,
        posted_date=date(2026, 3, 1),
    )
    model_session.add(paper)
    await model_session.flush()

    log_entry = AssessmentLog(
        paper_id=paper.id,
        stage="coarse_filter",
        model_used="claude-haiku-4-5-20251001",
        prompt_version="v1.0",
        prompt_text="You are a biosecurity screening assistant...",
        raw_response='{"relevant": true, "confidence": 0.95}',
        parsed_result={"relevant": True, "confidence": 0.95},
        input_tokens=150,
        output_tokens=25,
        cost_estimate_usd=0.0001,
    )
    model_session.add(log_entry)
    await model_session.flush()

    result = await model_session.execute(
        select(AssessmentLog).where(AssessmentLog.paper_id == paper.id)
    )
    row = result.scalar_one()
    assert row.stage == "coarse_filter"
    assert row.parsed_result == {"relevant": True, "confidence": 0.95}
    assert row.input_tokens == 150
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'pipeline.models'`

- [ ] **Step 3: Implement `pipeline/models.py`**

```python
"""SQLAlchemy ORM models for the DURC triage pipeline.

Three tables:
- papers: main record for each ingested paper
- paper_groups: links duplicate/related paper records
- assessment_logs: append-only audit trail of every LLM classification
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Cross-database JSON: renders as JSONB on PostgreSQL, JSON on SQLite/others.
PlatformJSON = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SourceServer(str, enum.Enum):
    BIORXIV = "biorxiv"
    MEDRXIV = "medrxiv"
    EUROPEPMC = "europepmc"
    PUBMED = "pubmed"
    ARXIV = "arxiv"
    RESEARCH_SQUARE = "research_square"
    CHEMRXIV = "chemrxiv"
    ZENODO = "zenodo"
    SSRN = "ssrn"


class PipelineStage(str, enum.Enum):
    INGESTED = "ingested"
    COARSE_FILTERED = "coarse_filtered"
    FULLTEXT_RETRIEVED = "fulltext_retrieved"
    METHODS_ANALYSED = "methods_analysed"
    ADJUDICATED = "adjudicated"


class RiskTier(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendedAction(str, enum.Enum):
    ARCHIVE = "archive"
    MONITOR = "monitor"
    REVIEW = "review"
    ESCALATE = "escalate"


class ReviewStatus(str, enum.Enum):
    UNREVIEWED = "unreviewed"
    UNDER_REVIEW = "under_review"
    CONFIRMED_CONCERN = "confirmed_concern"
    FALSE_POSITIVE = "false_positive"
    ARCHIVED = "archived"


class DedupRelationship(str, enum.Enum):
    DUPLICATE = "duplicate"
    PUBLISHED_VERSION = "published_version"
    UPDATED_VERSION = "updated_version"
    CROSS_POSTED = "cross_posted"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    doi: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[list | dict | None] = mapped_column(PlatformJSON, nullable=False, default=list)
    corresponding_author: Mapped[str | None] = mapped_column(String(512))
    corresponding_institution: Mapped[str | None] = mapped_column(String(512))
    abstract: Mapped[str | None] = mapped_column(Text)
    source_server: Mapped[SourceServer] = mapped_column(
        SQLEnum(SourceServer, name="source_server", create_constraint=True),
    )
    posted_date: Mapped[date] = mapped_column(Date, index=True)
    subject_category: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Full text (populated in later pipeline stages)
    full_text_url: Mapped[str | None] = mapped_column(Text)
    full_text_retrieved: Mapped[bool] = mapped_column(Boolean, default=False)
    full_text_content: Mapped[str | None] = mapped_column(Text)
    methods_section: Mapped[str | None] = mapped_column(Text)

    # Pipeline state
    pipeline_stage: Mapped[PipelineStage] = mapped_column(
        SQLEnum(PipelineStage, name="pipeline_stage", create_constraint=True),
        default=PipelineStage.INGESTED,
        index=True,
    )

    # Classification results (latest only; history in assessment_logs)
    stage1_result: Mapped[dict | None] = mapped_column(PlatformJSON)
    stage2_result: Mapped[dict | None] = mapped_column(PlatformJSON)
    stage3_result: Mapped[dict | None] = mapped_column(PlatformJSON)
    risk_tier: Mapped[RiskTier | None] = mapped_column(
        SQLEnum(RiskTier, name="risk_tier", create_constraint=True),
        index=True,
    )
    recommended_action: Mapped[RecommendedAction | None] = mapped_column(
        SQLEnum(RecommendedAction, name="recommended_action", create_constraint=True),
    )
    aggregate_score: Mapped[int | None] = mapped_column(Integer)

    # Analyst workflow
    review_status: Mapped[ReviewStatus] = mapped_column(
        SQLEnum(ReviewStatus, name="review_status", create_constraint=True),
        default=ReviewStatus.UNREVIEWED,
        index=True,
    )
    analyst_notes: Mapped[str | None] = mapped_column(Text)

    # Dedup
    is_duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("papers.id"),
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PaperGroup(Base):
    __tablename__ = "paper_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    canonical_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id"), index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id"), index=True)
    relationship: Mapped[DedupRelationship] = mapped_column(
        SQLEnum(DedupRelationship, name="dedup_relationship", create_constraint=True),
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    strategy_used: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("canonical_id", "member_id", name="uq_paper_group_pair"),
    )


class AssessmentLog(Base):
    __tablename__ = "assessment_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id"), index=True)
    stage: Mapped[str] = mapped_column(String(50), index=True)
    model_used: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    prompt_text: Mapped[str] = mapped_column(Text)
    raw_response: Mapped[str] = mapped_column(Text)
    parsed_result: Mapped[dict | None] = mapped_column(PlatformJSON)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_estimate_usd: Mapped[float] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_models.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/models.py tests/test_models.py
git commit -m "feat: add SQLAlchemy models for Paper, PaperGroup, AssessmentLog"
```

---

## Task 4: Database Session Manager

**Files:**
- Create: `pipeline/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_db.py`:

```python
"""Tests for pipeline.db — async session factory with commit/rollback."""

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from pipeline.db import get_session, make_engine, make_session_factory
from pipeline.models import Base, Paper, SourceServer

from datetime import date


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'pipeline.db'`

- [ ] **Step 3: Implement `pipeline/db.py`**

```python
"""Async database engine and session factory.

Usage:
    async with get_session() as session:
        result = await session.execute(select(Paper))

For tests, pass a custom factory:
    factory = async_sessionmaker(test_engine, ...)
    async with get_session(factory=factory) as session:
        ...
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_db.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/db.py tests/test_db.py
git commit -m "feat: add async session manager with auto-commit/rollback"
```

---

## Task 5: Test Infrastructure — conftest & Fixtures

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/fixtures/sample_biorxiv.json`

- [ ] **Step 1: Create `tests/conftest.py`**

Shared fixtures and factory functions used by ingest and dedup tests.

```python
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
```

- [ ] **Step 2: Create `tests/fixtures/sample_biorxiv.json`**

```json
{
  "messages": [{"status": "ok", "count": 10, "total": 10}],
  "collection": [
    {
      "doi": "10.1101/2026.03.15.500001",
      "title": "Population dynamics of migratory songbirds in temperate forests",
      "authors": "Chen, L.; Morales, R.; Dubois, P.",
      "author_corresponding": "Lin Chen",
      "author_corresponding_institution": "Cornell Lab of Ornithology",
      "date": "2026-03-15",
      "version": "1",
      "category": "ecology",
      "abstract": "We tracked 14 species of neotropical migratory songbirds across three breeding seasons using automated radio telemetry arrays. Our data reveal significant shifts in arrival phenology correlated with spring temperature anomalies. We model population-level consequences of phenological mismatch with peak arthropod availability.",
      "published": "NA",
      "server": "biorxiv"
    },
    {
      "doi": "10.1101/2026.03.15.500002",
      "title": "Crystal structure of human ACE2 bound to a computationally designed miniprotein inhibitor",
      "authors": "Nakamura, T.; Fischer, K.; Okonkwo, E.",
      "author_corresponding": "Takeshi Nakamura",
      "author_corresponding_institution": "University of Tokyo",
      "date": "2026-03-15",
      "version": "1",
      "category": "biophysics",
      "abstract": "We report the 1.8 &Aring; crystal structure of human ACE2 in complex with a de novo designed 56-residue miniprotein that blocks SARS-CoV-2 spike binding. The miniprotein achieves sub-nanomolar affinity through an optimised helical interface. These structural data inform next-generation inhaled antivirals.",
      "published": "NA",
      "server": "biorxiv"
    },
    {
      "doi": "10.1101/2026.03.15.500003",
      "title": "Directed evolution of a broadly neutralising antibody against influenza B neuraminidase",
      "authors": "Patel, S.; Yamamoto, H.; Garcia, M.",
      "author_corresponding": "Sanjay Patel",
      "author_corresponding_institution": "Scripps Research Institute",
      "date": "2026-03-16",
      "version": "1",
      "category": "immunology",
      "abstract": "Using a yeast surface display platform, we evolved a human monoclonal antibody to bind conserved epitopes on influenza B neuraminidase across both Victoria and Yamagata lineages. We characterised escape mutations and mapped residues critical for immune evasion.",
      "published": "NA",
      "server": "biorxiv"
    },
    {
      "doi": "10.1101/2026.03.15.500004",
      "title": "A simplified reverse genetics system for generating recombinant H5N1 influenza viruses",
      "authors": "Kim, D.; Volkov, A.; Petersen, N.",
      "author_corresponding": "Daeho Kim",
      "author_corresponding_institution": "Korea Advanced Institute of Science and Technology",
      "date": "2026-03-16",
      "version": "1",
      "category": "microbiology",
      "abstract": "We present a streamlined eight-plasmid reverse genetics system for generating recombinant H5N1 avian influenza viruses in standard BSL-3 facilities. Our approach reduces the cloning steps from twelve to four and achieves 10-fold higher rescue efficiency than existing protocols. We demonstrate the system by introducing targeted mutations in the HA and PB2 genes.",
      "published": "NA",
      "server": "biorxiv"
    },
    {
      "doi": "10.1101/2026.03.15.500005",
      "title": "Single-cell RNA sequencing of murine intestinal epithelium reveals novel stem cell markers",
      "authors": "O'Brien, K.; Johansson, S.; Li, W.",
      "author_corresponding": "Katherine O'Brien",
      "author_corresponding_institution": "Karolinska Institute",
      "date": "2026-03-16",
      "version": "1",
      "category": "cell biology",
      "abstract": "We performed single-cell RNA sequencing on 45,000 cells from murine small intestinal crypts, identifying twelve transcriptionally distinct populations. We describe three previously uncharacterised stem cell subsets defined by co-expression of Lgr5 and novel surface markers amenable to FACS isolation.",
      "published": "NA",
      "server": "biorxiv"
    },
    {
      "doi": "10.1101/2026.03.15.500006",
      "title": "De novo design of a protein toxin inhibitor using deep learning-guided backbone generation",
      "authors": "Zheng, Y.; Adeyemi, F.; Larsson, M.",
      "author_corresponding": "Yichen Zheng",
      "author_corresponding_institution": "Institute for Protein Design, University of Washington",
      "date": "2026-03-17",
      "version": "1",
      "category": "synthetic biology",
      "abstract": "We used RFdiffusion to design de novo protein binders targeting the receptor-binding domain of Clostridium botulinum neurotoxin serotype A. The top designs achieved picomolar binding affinity and neutralised toxin activity in cell-based assays. We provide the complete computational pipeline and all protein sequences.",
      "published": "NA",
      "server": "biorxiv"
    },
    {
      "doi": "10.1101/2026.03.15.500007",
      "title": "Metagenomic surveillance of novel bat coronaviruses in Southeast Asian cave systems",
      "authors": "Tran, V.; Suryadi, B.; Martinez, C.",
      "author_corresponding": "Vinh Tran",
      "author_corresponding_institution": "Pasteur Institute Ho Chi Minh City",
      "date": "2026-03-17",
      "version": "1",
      "category": "microbiology",
      "abstract": "We conducted longitudinal metagenomic surveillance of horseshoe bat colonies across 23 cave sites in Vietnam and Indonesia over 18 months. We identified 14 novel sarbecoviruses, three of which utilise human ACE2 for cell entry in pseudovirus assays. Full genome sequences and receptor binding characterisation data are provided.",
      "published": "NA",
      "server": "biorxiv"
    },
    {
      "doi": "10.1101/2026.03.15.500008",
      "title": "Improved methods for large-scale CRISPR screens in primary human T cells",
      "authors": "Anderson, R.; Mbeki, T.; Fujita, S.",
      "author_corresponding": "Rachel Anderson",
      "author_corresponding_institution": "Broad Institute of MIT and Harvard",
      "date": "2026-03-17",
      "version": "2",
      "category": "genomics",
      "abstract": "We describe an optimised lentiviral delivery protocol for genome-wide CRISPR-Cas9 screens in primary human CD4+ and CD8+ T cells. Our approach achieves 85% editing efficiency with minimal toxicity, enabling identification of genes essential for T cell activation, exhaustion, and cytokine production.",
      "published": "NA",
      "server": "biorxiv"
    },
    {
      "doi": "10.1101/2026.03.15.500009",
      "title": "Bayesian phylogeographic analysis of H5N1 clade 2.3.4.4b spread in North American wild birds",
      "authors": "Williams, D.; Park, J.; Osei, A.",
      "author_corresponding": "David Williams",
      "author_corresponding_institution": "USGS National Wildlife Health Center",
      "date": "2026-03-18",
      "version": "1",
      "category": "epidemiology",
      "abstract": "We reconstructed the spatiotemporal dynamics of HPAI H5N1 clade 2.3.4.4b dissemination across North American flyways using 2,400 complete genomes collected between 2021 and 2025. Bayesian phylogeographic models identify the Mississippi flyway as the primary corridor for southward spread, with three independent introductions from Eurasia.",
      "published": "NA",
      "server": "biorxiv"
    },
    {
      "doi": "10.1101/2026.03.15.500010",
      "title": "A transformer-based model for predicting antimicrobial resistance from whole-genome sequences",
      "authors": "Gupta, A.; Nilsson, E.; da Silva, R.",
      "author_corresponding": "Ananya Gupta",
      "author_corresponding_institution": "European Bioinformatics Institute",
      "date": "2026-03-18",
      "version": "1",
      "category": "bioinformatics",
      "abstract": "We present AMRFormer, a transformer architecture trained on 120,000 bacterial whole-genome sequences with paired phenotypic resistance data across 15 antibiotic classes. The model achieves 94.2% accuracy in predicting resistance profiles from raw assemblies and identifies novel candidate resistance determinants in Klebsiella pneumoniae.",
      "published": "NA",
      "server": "biorxiv"
    }
  ]
}
```

- [ ] **Step 3: Verify pytest can discover fixtures**

```bash
uv run pytest --co -q
```

Expected: lists all test functions discovered so far (from test_config.py, test_models.py, test_db.py).

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/fixtures/sample_biorxiv.json
git commit -m "feat: add shared test fixtures and sample bioRxiv API data"
```

---

## Task 6: bioRxiv Client — Normalisation

**Files:**
- Create: `pipeline/ingest/biorxiv.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing tests for normalisation**

Create `tests/test_ingest.py`:

```python
"""Tests for pipeline.ingest.biorxiv — CSHL API client."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from tests.conftest import make_api_response, make_collection, make_raw_record


class TestNormalise:
    """Tests for BiorxivClient._normalise field mapping."""

    def _make_client(self, server: str = "biorxiv"):
        from pipeline.ingest.biorxiv import BiorxivClient
        return BiorxivClient(server=server, request_delay=0)

    def test_basic_field_mapping(self):
        client = self._make_client()
        raw = make_raw_record(
            doi="10.1101/2026.03.15.500001",
            title="  Test Title With Spaces  ",
            authors="Smith, J.; Jones, A.; Brown, B.",
            date_str="2026-03-15",
            version="2",
            category="microbiology",
            server="biorxiv",
        )
        result = client._normalise(raw)

        assert result["doi"] == "10.1101/2026.03.15.500001"
        assert result["title"] == "Test Title With Spaces"  # stripped
        assert result["authors"] == [
            {"name": "Smith, J."},
            {"name": "Jones, A."},
            {"name": "Brown, B."},
        ]
        assert result["posted_date"] == date(2026, 3, 15)
        assert result["version"] == 2
        assert result["source_server"] == "biorxiv"
        assert result["subject_category"] == "microbiology"

    def test_html_entity_decoding_in_abstract(self):
        client = self._make_client()
        raw = make_raw_record(
            abstract="The 1.8 &Aring; structure of ACE2 shows &lt;50% occupancy &amp; high B-factors."
        )
        result = client._normalise(raw)
        assert "\u00c5" in result["abstract"]  # Angstrom symbol decoded
        assert "<50%" in result["abstract"]
        assert "& high" in result["abstract"]

    def test_corresponding_author_fields(self):
        client = self._make_client()
        raw = make_raw_record(
            author_corresponding="Sanjay Patel",
            author_corresponding_institution="Scripps Research Institute",
        )
        result = client._normalise(raw)
        assert result["corresponding_author"] == "Sanjay Patel"
        assert result["corresponding_institution"] == "Scripps Research Institute"

    def test_medrxiv_source_server(self):
        client = self._make_client(server="medrxiv")
        raw = make_raw_record(server="medrxiv")
        result = client._normalise(raw)
        assert result["source_server"] == "medrxiv"

    def test_jatsxml_maps_to_full_text_url(self):
        client = self._make_client()
        raw = make_raw_record(
            jatsxml="https://www.biorxiv.org/content/10.1101/2026.03.15.500001v1.source.xml"
        )
        result = client._normalise(raw)
        assert result["full_text_url"] == "https://www.biorxiv.org/content/10.1101/2026.03.15.500001v1.source.xml"

    def test_missing_jatsxml_gives_none(self):
        client = self._make_client()
        raw = make_raw_record()  # no jatsxml key
        result = client._normalise(raw)
        assert result["full_text_url"] is None

    def test_empty_authors_string(self):
        client = self._make_client()
        raw = make_raw_record(authors="")
        result = client._normalise(raw)
        assert result["authors"] == []

    def test_single_author(self):
        client = self._make_client()
        raw = make_raw_record(authors="Solo, H.")
        result = client._normalise(raw)
        assert result["authors"] == [{"name": "Solo, H."}]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_ingest.py::TestNormalise -v
```

Expected: `ModuleNotFoundError: No module named 'pipeline.ingest.biorxiv'`

- [ ] **Step 3: Implement `pipeline/ingest/biorxiv.py` — normalisation only (client shell)**

```python
"""Async client for the CSHL bioRxiv/medRxiv API.

Usage:
    async with BiorxivClient(server="biorxiv") as client:
        async for paper in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30)):
            print(paper["title"])
"""

from __future__ import annotations

import asyncio
import html
from datetime import date
from typing import TYPE_CHECKING, AsyncGenerator, Literal

import httpx
import structlog

if TYPE_CHECKING:
    pass

log = structlog.get_logger()


class BiorxivClient:
    """Async client for bioRxiv and medRxiv via the shared CSHL API."""

    BASE_URL = "https://api.biorxiv.org/details"
    PAGE_SIZE = 100

    def __init__(
        self,
        server: Literal["biorxiv", "medrxiv"],
        request_delay: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        self.server = server
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> BiorxivClient:
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # -- Public API ----------------------------------------------------------

    async def fetch_papers(
        self, from_date: date, to_date: date
    ) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts, paginating through all results."""
        # Implemented in Task 7
        raise NotImplementedError
        yield  # Make this a generator  # noqa: E711

    # -- Internal ------------------------------------------------------------

    async def _fetch_page(
        self, from_date: date, to_date: date, cursor: int
    ) -> dict:
        """Fetch a single page from the API with retry and backoff."""
        # Implemented in Task 7
        raise NotImplementedError

    def _normalise(self, raw: dict) -> dict:
        """Map a raw CSHL API record to the common metadata schema."""
        authors_str = raw.get("authors", "")
        authors_list = [
            {"name": a.strip()} for a in authors_str.split(";") if a.strip()
        ]

        return {
            "doi": raw.get("doi"),
            "title": raw.get("title", "").strip(),
            "authors": authors_list,
            "corresponding_author": raw.get("author_corresponding"),
            "corresponding_institution": raw.get("author_corresponding_institution"),
            "abstract": html.unescape(raw.get("abstract", "")),
            "source_server": self.server,
            "posted_date": date.fromisoformat(raw["date"]),
            "subject_category": raw.get("category"),
            "version": int(raw.get("version", 1)),
            "full_text_url": raw.get("jatsxml"),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_ingest.py::TestNormalise -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/ingest/biorxiv.py tests/test_ingest.py
git commit -m "feat: add BiorxivClient with field normalisation"
```

---

## Task 7: bioRxiv Client — Fetch & Pagination

**Files:**
- Modify: `pipeline/ingest/biorxiv.py`
- Modify: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing tests for fetch and pagination**

Append to `tests/test_ingest.py`:

```python
class TestFetch:
    """Tests for BiorxivClient.fetch_papers — HTTP fetch + pagination."""

    @respx.mock
    async def test_fetch_single_page(self):
        """Fetch fewer than 100 results — single page, no pagination."""
        collection = make_collection(3)
        response = make_api_response(collection, total=3)

        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-02/0").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 2))]

        assert len(papers) == 3
        assert papers[0]["doi"] == "10.1101/2026.03.01.100000"
        assert papers[0]["source_server"] == "biorxiv"

    @respx.mock
    async def test_fetch_multiple_pages(self):
        """Fetch 250 results — should paginate across 3 pages (100+100+50)."""
        page1 = make_api_response(make_collection(100, start_idx=0), total=250)
        page2 = make_api_response(make_collection(100, start_idx=100), total=250)
        page3 = make_api_response(make_collection(50, start_idx=200), total=250)

        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-30/0").mock(
            return_value=httpx.Response(200, json=page1)
        )
        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-30/100").mock(
            return_value=httpx.Response(200, json=page2)
        )
        respx.get("https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-30/200").mock(
            return_value=httpx.Response(200, json=page3)
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 30))]

        assert len(papers) == 250
        # First paper from page 1
        assert papers[0]["doi"] == "10.1101/2026.03.01.100000"
        # First paper from page 3
        assert papers[200]["doi"] == "10.1101/2026.03.01.100200"

    @respx.mock
    async def test_fetch_empty_result(self):
        """No papers found for date range — yields nothing."""
        response = make_api_response([], total=0)

        respx.get("https://api.biorxiv.org/details/biorxiv/2026-01-01/2026-01-01/0").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 1, 1), date(2026, 1, 1))]

        assert len(papers) == 0

    @respx.mock
    async def test_medrxiv_url(self):
        """medRxiv client hits /medrxiv/ endpoint."""
        response = make_api_response(make_collection(1, server="medrxiv"), total=1)

        route = respx.get("https://api.biorxiv.org/details/medrxiv/2026-03-01/2026-03-01/0").mock(
            return_value=httpx.Response(200, json=response)
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="medrxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert route.called
        assert len(papers) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_ingest.py::TestFetch -v
```

Expected: `NotImplementedError`

- [ ] **Step 3: Implement `fetch_papers` and `_fetch_page` in `pipeline/ingest/biorxiv.py`**

Replace the placeholder `fetch_papers` and `_fetch_page` methods:

```python
    async def fetch_papers(
        self, from_date: date, to_date: date
    ) -> AsyncGenerator[dict, None]:
        """Yield normalised paper dicts, paginating through all results."""
        cursor = 0
        while True:
            data = await self._fetch_page(from_date, to_date, cursor)
            messages = data.get("messages", [{}])
            if not messages:
                break

            msg = messages[0]
            total = msg.get("total", 0)
            count = msg.get("count", 0)

            for raw in data.get("collection", []):
                yield self._normalise(raw)

            cursor += self.PAGE_SIZE
            if count < self.PAGE_SIZE or cursor >= total:
                break

            log.info(
                "page_fetched",
                server=self.server,
                cursor=cursor,
                total=total,
                fetched_this_page=count,
            )

    async def _fetch_page(
        self, from_date: date, to_date: date, cursor: int
    ) -> dict:
        """Fetch a single page from the API with retry and backoff."""
        assert self._client is not None, "Use BiorxivClient as async context manager"
        url = f"{self.BASE_URL}/{self.server}/{from_date}/{to_date}/{cursor}"

        for attempt in range(1, self.max_retries + 1):
            await asyncio.sleep(self.request_delay)
            try:
                resp = await self._client.get(url, timeout=30.0)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 503):
                    backoff = min(2**attempt, 30)
                    log.warning(
                        "rate_limited",
                        url=url,
                        status=resp.status_code,
                        attempt=attempt,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                resp.raise_for_status()
            except httpx.TimeoutException:
                if attempt == self.max_retries:
                    raise
                backoff = min(2**attempt, 30)
                log.warning("timeout", url=url, attempt=attempt, backoff=backoff)
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Failed after {self.max_retries} retries: {url}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_ingest.py -v
```

Expected: All 12 tests pass (8 normalise + 4 fetch).

- [ ] **Step 5: Commit**

```bash
git add pipeline/ingest/biorxiv.py tests/test_ingest.py
git commit -m "feat: add paginated fetch with rate-limit delay for bioRxiv/medRxiv"
```

---

## Task 8: bioRxiv Client — Retry Logic

**Files:**
- Modify: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing tests for retry behaviour**

Append to `tests/test_ingest.py`:

```python
class TestRetry:
    """Tests for BiorxivClient retry and error handling."""

    @respx.mock
    async def test_rate_limit_429_retries_then_succeeds(self):
        """A 429 on first attempt triggers backoff, second attempt succeeds."""
        collection = make_collection(1)
        ok_response = make_api_response(collection, total=1)

        url = "https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-01/0"
        route = respx.get(url).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=ok_response),
            ]
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 1
        assert route.call_count == 2

    @respx.mock
    async def test_503_retries_then_succeeds(self):
        """A 503 on first attempt triggers backoff, second attempt succeeds."""
        collection = make_collection(1)
        ok_response = make_api_response(collection, total=1)

        url = "https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-01/0"
        route = respx.get(url).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json=ok_response),
            ]
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 1
        assert route.call_count == 2

    @respx.mock
    async def test_timeout_retries_then_succeeds(self):
        """A timeout on first attempt retries, second attempt succeeds."""
        collection = make_collection(1)
        ok_response = make_api_response(collection, total=1)

        url = "https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-01/0"
        route = respx.get(url).mock(
            side_effect=[
                httpx.TimeoutException("connect timeout"),
                httpx.Response(200, json=ok_response),
            ]
        )

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            papers = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert len(papers) == 1
        assert route.call_count == 2

    @respx.mock
    async def test_all_retries_exhausted_raises(self):
        """If all retries fail with 429, RuntimeError is raised."""
        url = "https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-01/0"
        respx.get(url).mock(return_value=httpx.Response(429))

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0, max_retries=2) as client:
            with pytest.raises(RuntimeError, match="Failed after 2 retries"):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

    @respx.mock
    async def test_non_retryable_error_raises_immediately(self):
        """A 404 is not retried — raises httpx.HTTPStatusError immediately."""
        url = "https://api.biorxiv.org/details/biorxiv/2026-03-01/2026-03-01/0"
        route = respx.get(url).mock(return_value=httpx.Response(404))

        from pipeline.ingest.biorxiv import BiorxivClient

        async with BiorxivClient(server="biorxiv", request_delay=0) as client:
            with pytest.raises(httpx.HTTPStatusError):
                _ = [p async for p in client.fetch_papers(date(2026, 3, 1), date(2026, 3, 1))]

        assert route.call_count == 1  # No retries
```

- [ ] **Step 2: Run tests to verify they pass**

The retry logic was already implemented in Task 7's `_fetch_page`. These tests should pass immediately:

```bash
uv run pytest tests/test_ingest.py::TestRetry -v
```

Expected: 5 passed.

- [ ] **Step 3: Run the full ingest test suite**

```bash
uv run pytest tests/test_ingest.py -v
```

Expected: 17 passed (8 normalise + 4 fetch + 5 retry).

- [ ] **Step 4: Commit**

```bash
git add tests/test_ingest.py
git commit -m "test: add retry and error handling tests for bioRxiv client"
```

---

## Task 9: Dedup — DOI Match

**Files:**
- Create: `pipeline/ingest/dedup.py`
- Create: `tests/test_dedup.py`

- [ ] **Step 1: Write the failing tests for DOI matching**

Create `tests/test_dedup.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_dedup.py::TestDoiMatch -v
```

Expected: `ModuleNotFoundError: No module named 'pipeline.ingest.dedup'`

- [ ] **Step 3: Implement `pipeline/ingest/dedup.py` — DedupResult and DOI matching**

```python
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

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.models import DedupRelationship, Paper, PaperGroup

import structlog

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
        Implemented in Task 10.
        """
        return None

    async def record_duplicate(
        self,
        canonical_id: uuid.UUID,
        member_id: uuid.UUID,
        result: DedupResult,
        relationship: DedupRelationship = DedupRelationship.DUPLICATE,
    ) -> None:
        """Create a PaperGroup entry and set is_duplicate_of on the member."""
        # Implemented in Task 11
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_dedup.py::TestDoiMatch -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/ingest/dedup.py tests/test_dedup.py
git commit -m "feat: add dedup engine with DOI exact-match (tier 1)"
```

---

## Task 10: Dedup — Fuzzy Title/Author Matching

**Files:**
- Modify: `pipeline/ingest/dedup.py`
- Modify: `tests/test_dedup.py`

- [ ] **Step 1: Write the failing tests for fuzzy matching**

Append to `tests/test_dedup.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_dedup.py::TestTitleAuthorSimilarity -v
```

Expected: Failures — `_check_title_author` returns `None` (placeholder).

- [ ] **Step 3: Implement `_check_title_author` in `pipeline/ingest/dedup.py`**

Replace the placeholder `_find_title_author_match`:

```python
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

        stmt = (
            select(Paper.id, Paper.title, Paper.authors)
            .where(Paper.posted_date.between(date_from, date_to))
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_dedup.py -v
```

Expected: 7 passed (3 DOI + 4 fuzzy).

- [ ] **Step 5: Commit**

```bash
git add pipeline/ingest/dedup.py tests/test_dedup.py
git commit -m "feat: add fuzzy title/author dedup matching (tier 2)"
```

---

## Task 11: Dedup — DOI-less Fallback & Recording

**Files:**
- Modify: `pipeline/ingest/dedup.py`
- Modify: `tests/test_dedup.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dedup.py`:

```python
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
        stmt = select(Paper).where(Paper.id == p2.id)
        result = await db_session.execute(stmt)
        updated = result.scalar_one()
        assert updated.is_duplicate_of == p1.id
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_dedup.py::TestDoiLessFallback tests/test_dedup.py::TestRecordDuplicate -v
```

Expected: `TestDoiLessFallback` may pass (reuses Tier 2 logic with different params). `TestRecordDuplicate` fails — `record_duplicate` is a no-op placeholder.

- [ ] **Step 3: Implement `record_duplicate` in `pipeline/ingest/dedup.py`**

Replace the placeholder `record_duplicate`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_dedup.py -v
```

Expected: 11 passed (3 DOI + 4 fuzzy + 2 DOI-less + 2 recording).

- [ ] **Step 5: Commit**

```bash
git add pipeline/ingest/dedup.py tests/test_dedup.py
git commit -m "feat: add DOI-less dedup fallback and PaperGroup recording"
```

---

## Task 12: Alembic Setup & Full Verification

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/` (initial migration)

- [ ] **Step 1: Initialize Alembic**

```bash
uv run alembic init alembic
```

This creates `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/`.

- [ ] **Step 2: Configure `alembic.ini`**

Edit `alembic.ini` — set the `sqlalchemy.url` line to read from the env:

```ini
# In alembic.ini, the sqlalchemy.url is overridden by env.py.
# Set a placeholder here; the real URL comes from pipeline.config.
sqlalchemy.url = postgresql+asyncpg://durc:durc_local@localhost:5432/durc_triage
```

- [ ] **Step 3: Replace `alembic/env.py` with async-capable version**

```python
"""Alembic async migration environment.

Reads the database URL from pipeline.config and uses the async engine.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from pipeline.config import get_settings
from pipeline.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout."""
    url = get_settings().database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using an async engine."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_settings().database_url
    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Generate the initial migration**

Requires a running PostgreSQL (start with docker-compose) and a `.env` file:

```bash
cp .env.example .env
# Edit .env to set a real ANTHROPIC_API_KEY (or any placeholder for now)
docker compose up -d
# Wait for postgres to be ready
sleep 3
uv run alembic revision --autogenerate -m "initial schema"
```

Expected: creates a migration file in `alembic/versions/` with `create_table` for `papers`, `paper_groups`, `assessment_logs`.

- [ ] **Step 5: Edit the generated migration to add pg_trgm and GIN indexes**

At the top of the `upgrade()` function in the generated migration, add:

```python
def upgrade() -> None:
    # Enable trigram extension for fuzzy search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ... (auto-generated table creation statements) ...

    # GIN trigram index for fuzzy title search (dedup + dashboard)
    op.execute(
        "CREATE INDEX ix_papers_title_trgm ON papers USING gin (title gin_trgm_ops)"
    )
    # GIN tsvector index for full-text search on title + abstract
    op.execute(
        "CREATE INDEX ix_papers_tsv ON papers USING gin ("
        "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, ''))"
        ")"
    )
```

In the `downgrade()` function:

```python
def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_papers_tsv")
    op.execute("DROP INDEX IF EXISTS ix_papers_title_trgm")
    # ... (auto-generated drop statements) ...
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
```

- [ ] **Step 6: Apply the migration**

```bash
uv run alembic upgrade head
```

Expected: tables created in local PostgreSQL.

- [ ] **Step 7: Run the full test suite**

```bash
uv run pytest -v
```

Expected: All tests pass (across test_config, test_models, test_db, test_ingest, test_dedup).

- [ ] **Step 8: Lint check**

```bash
uv run ruff check pipeline/ tests/
uv run ruff format --check pipeline/ tests/
```

Expected: No errors. Fix any issues before committing.

- [ ] **Step 9: Final commit**

```bash
git add alembic/ alembic.ini
git commit -m "feat: add Alembic async migrations with pg_trgm and GIN indexes"
```

- [ ] **Step 10: Tag Phase 1 completion**

```bash
git tag phase1-complete
```