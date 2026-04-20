"""SQLAlchemy ORM models for the DURC triage pipeline.

Six tables:
- papers: main record for each ingested paper
- paper_groups: links duplicate/related paper records
- assessment_logs: append-only audit trail of every LLM classification
- pipeline_runs: tracks each pipeline execution with counters and cost
- users: dashboard users (created on OAuth login)
- pipeline_settings: single-row table for dashboard-editable pipeline config
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as _SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def SQLEnum(enum_cls, **kw):
    """Ensure StrEnum values (lowercase) are sent to Postgres, not names."""
    kw.setdefault("values_callable", lambda e: [m.value for m in e])
    return _SQLEnum(enum_cls, **kw)


# Cross-database JSON: renders as JSONB on PostgreSQL, JSON on SQLite/others.
PlatformJSON = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SourceServer(enum.StrEnum):
    BIORXIV = "biorxiv"
    MEDRXIV = "medrxiv"
    EUROPEPMC = "europepmc"
    PUBMED = "pubmed"
    ARXIV = "arxiv"
    RESEARCH_SQUARE = "research_square"
    CHEMRXIV = "chemrxiv"
    ZENODO = "zenodo"
    SSRN = "ssrn"


class PipelineStage(enum.StrEnum):
    INGESTED = "ingested"
    COARSE_FILTERED = "coarse_filtered"
    FULLTEXT_RETRIEVED = "fulltext_retrieved"
    METHODS_ANALYSED = "methods_analysed"
    ADJUDICATED = "adjudicated"


class RiskTier(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendedAction(enum.StrEnum):
    ARCHIVE = "archive"
    MONITOR = "monitor"
    REVIEW = "review"
    ESCALATE = "escalate"


class ReviewStatus(enum.StrEnum):
    UNREVIEWED = "unreviewed"
    UNDER_REVIEW = "under_review"
    CONFIRMED_CONCERN = "confirmed_concern"
    FALSE_POSITIVE = "false_positive"
    ARCHIVED = "archived"


class DedupRelationship(enum.StrEnum):
    DUPLICATE = "duplicate"
    PUBLISHED_VERSION = "published_version"
    UPDATED_VERSION = "updated_version"
    CROSS_POSTED = "cross_posted"


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"


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
    language: Mapped[str | None] = mapped_column(String(10), index=True)
    original_title: Mapped[str | None] = mapped_column(Text)
    original_abstract: Mapped[str | None] = mapped_column(Text)
    original_methods_section: Mapped[str | None] = mapped_column(Text)

    # Full text (populated in later pipeline stages)
    full_text_url: Mapped[str | None] = mapped_column(Text)
    full_text_retrieved: Mapped[bool] = mapped_column(Boolean, default=False)
    full_text_content: Mapped[str | None] = mapped_column(Text)
    methods_section: Mapped[str | None] = mapped_column(Text)
    enrichment_data: Mapped[dict | None] = mapped_column(PlatformJSON)

    # Pipeline state
    pipeline_stage: Mapped[PipelineStage] = mapped_column(
        SQLEnum(PipelineStage, name="pipeline_stage", create_constraint=True),
        default=PipelineStage.INGESTED,
        index=True,
    )

    # Coarse filter gate — only papers that pass advance to fulltext+
    coarse_filter_passed: Mapped[bool | None] = mapped_column(Boolean, index=True)

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
    # TODO: Add reviewed_by (user ID) and status change audit log for analyst attribution.
    #       This should be a ForeignKey to users.id recording which analyst changed the
    #       review_status, plus a separate review_status_history table or JSONB column
    #       tracking all status transitions with timestamps and user IDs.
    review_status: Mapped[ReviewStatus] = mapped_column(
        SQLEnum(ReviewStatus, name="review_status", create_constraint=True),
        default=ReviewStatus.UNREVIEWED,
        index=True,
    )
    needs_manual_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
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

    __table_args__ = (
        Index("ix_papers_posted_date_stage", "posted_date", "pipeline_stage"),
        Index(
            "ix_papers_feed_query",
            "coarse_filter_passed", "is_duplicate_of", "risk_tier", "posted_date",
        ),
    )


class PaperGroup(Base):
    __tablename__ = "paper_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    canonical_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"),
        index=True,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"),
        index=True,
    )
    relationship: Mapped[DedupRelationship] = mapped_column(
        SQLEnum(DedupRelationship, name="dedup_relationship", create_constraint=True),
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    strategy_used: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (UniqueConstraint("canonical_id", "member_id", name="uq_paper_group_pair"),)


class AssessmentLog(Base):
    __tablename__ = "assessment_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"),
        index=True,
    )
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


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    papers_ingested: Mapped[int] = mapped_column(Integer, default=0)
    papers_after_dedup: Mapped[int] = mapped_column(Integer, default=0)
    papers_coarse_passed: Mapped[int] = mapped_column(Integer, default=0)
    papers_fulltext_retrieved: Mapped[int] = mapped_column(Integer, default=0)
    papers_methods_analysed: Mapped[int] = mapped_column(Integer, default=0)
    papers_enriched: Mapped[int] = mapped_column(Integer, default=0)
    papers_adjudicated: Mapped[int] = mapped_column(Integer, default=0)
    current_stage: Mapped[str | None] = mapped_column(String(50))
    pubmed_query_mode: Mapped[str | None] = mapped_column(String(20))
    pid: Mapped[int | None] = mapped_column(Integer)
    from_date: Mapped[date | None] = mapped_column(Date)
    to_date: Mapped[date | None] = mapped_column(Date)
    errors: Mapped[list | None] = mapped_column(PlatformJSON)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    trigger: Mapped[str] = mapped_column(String(50))
    backlog_stats: Mapped[dict | None] = mapped_column(PlatformJSON)


class User(Base):
    """Dashboard user (created on OAuth login)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str | None] = mapped_column(String(255))
    image: Mapped[str | None] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role", create_constraint=True),
        default=UserRole.ANALYST,
        server_default="analyst",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PipelineSettings(Base):
    """Single-row table for dashboard-editable pipeline config."""

    __tablename__ = "pipeline_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_pipeline_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    settings: Mapped[dict] = mapped_column(PlatformJSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
