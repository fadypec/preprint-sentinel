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
