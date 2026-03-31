"""Tests for pipeline.models — SQLAlchemy ORM models."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def test_create_all_succeeds(db_session: AsyncSession):
    """Base.metadata.create_all works without errors on SQLite."""
    result = await db_session.execute(select(1))
    assert result.scalar() == 1


async def test_paper_insert_and_read(db_session: AsyncSession):
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
    db_session.add(paper)
    await db_session.flush()

    result = await db_session.execute(select(Paper).where(Paper.doi == "10.1101/2026.03.01.123456"))
    row = result.scalar_one()

    assert isinstance(row.id, uuid.UUID)
    assert row.title == "Gain-of-function analysis of H5N1 transmissibility"
    assert row.authors == [{"name": "Smith, J."}, {"name": "Jones, A."}]
    assert row.source_server == SourceServer.BIORXIV
    assert row.posted_date == date(2026, 3, 1)
    assert row.pipeline_stage == PipelineStage.INGESTED
    assert row.review_status == ReviewStatus.UNREVIEWED
    assert row.is_duplicate_of is None


async def test_paper_group_insert(db_session: AsyncSession):
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
    db_session.add_all([p1, p2])
    await db_session.flush()

    group = PaperGroup(
        canonical_id=p1.id,
        member_id=p2.id,
        relationship=DedupRelationship.DUPLICATE,
        confidence=1.0,
        strategy_used="doi_match",
    )
    db_session.add(group)
    await db_session.flush()

    result = await db_session.execute(select(PaperGroup).where(PaperGroup.canonical_id == p1.id))
    row = result.scalar_one()
    assert row.member_id == p2.id
    assert row.relationship == DedupRelationship.DUPLICATE
    assert row.strategy_used == "doi_match"


async def test_assessment_log_insert(db_session: AsyncSession):
    """Insert an AssessmentLog entry and verify all fields persist."""
    from pipeline.models import AssessmentLog, Paper, SourceServer

    paper = Paper(
        doi="10.1101/2026.03.01.999999",
        title="Test paper",
        authors=[],
        source_server=SourceServer.BIORXIV,
        posted_date=date(2026, 3, 1),
    )
    db_session.add(paper)
    await db_session.flush()

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
    db_session.add(log_entry)
    await db_session.flush()

    result = await db_session.execute(
        select(AssessmentLog).where(AssessmentLog.paper_id == paper.id)
    )
    row = result.scalar_one()
    assert row.stage == "coarse_filter"
    assert row.parsed_result == {"relevant": True, "confidence": 0.95}
    assert row.input_tokens == 150


async def test_user_default_role(db_session: AsyncSession):
    """User.role defaults to ANALYST when not explicitly set."""
    from pipeline.models import User, UserRole

    user = User(
        email="analyst@example.com",
        name="Test Analyst",
    )
    db_session.add(user)
    await db_session.flush()

    result = await db_session.execute(select(User).where(User.email == "analyst@example.com"))
    row = result.scalar_one()

    assert row.role == UserRole.ANALYST


async def test_user_email_unique(db_session: AsyncSession):
    """Inserting two Users with the same email raises IntegrityError."""
    from pipeline.models import User

    user1 = User(email="duplicate@example.com", name="User One")
    user2 = User(email="duplicate@example.com", name="User Two")

    db_session.add(user1)
    await db_session.flush()

    db_session.add(user2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_pipeline_settings_insert_and_read(db_session: AsyncSession):
    """PipelineSettings with id=1 and a settings dict can be inserted and read back."""
    from pipeline.models import PipelineSettings

    config = {"coarse_filter_threshold": 0.8, "daily_run_hour": 6}
    settings = PipelineSettings(id=1, settings=config)
    db_session.add(settings)
    await db_session.flush()

    result = await db_session.execute(select(PipelineSettings).where(PipelineSettings.id == 1))
    row = result.scalar_one()

    assert row.id == 1
    assert row.settings == config
