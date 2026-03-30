"""initial schema

Revision ID: a0314de3b571
Revises:
Create Date: 2026-03-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a0314de3b571"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial tables, enums, extensions, and indexes."""

    # Enable trigram extension for fuzzy search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- papers table ---
    op.create_table(
        "papers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("corresponding_author", sa.String(length=512), nullable=True),
        sa.Column("corresponding_institution", sa.String(length=512), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column(
            "source_server",
            sa.Enum(
                "biorxiv",
                "medrxiv",
                "europepmc",
                "pubmed",
                "arxiv",
                "research_square",
                "chemrxiv",
                "zenodo",
                "ssrn",
                name="source_server",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("posted_date", sa.Date(), nullable=False),
        sa.Column("subject_category", sa.String(length=255), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("full_text_url", sa.Text(), nullable=True),
        sa.Column("full_text_retrieved", sa.Boolean(), nullable=False),
        sa.Column("full_text_content", sa.Text(), nullable=True),
        sa.Column("methods_section", sa.Text(), nullable=True),
        sa.Column(
            "pipeline_stage",
            sa.Enum(
                "ingested",
                "coarse_filtered",
                "fulltext_retrieved",
                "methods_analysed",
                "adjudicated",
                name="pipeline_stage",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("stage1_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stage2_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stage3_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "risk_tier",
            sa.Enum(
                "low",
                "medium",
                "high",
                "critical",
                name="risk_tier",
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "recommended_action",
            sa.Enum(
                "archive",
                "monitor",
                "review",
                "escalate",
                name="recommended_action",
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("aggregate_score", sa.Integer(), nullable=True),
        sa.Column(
            "review_status",
            sa.Enum(
                "unreviewed",
                "under_review",
                "confirmed_concern",
                "false_positive",
                "archived",
                name="review_status",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("analyst_notes", sa.Text(), nullable=True),
        sa.Column("is_duplicate_of", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["is_duplicate_of"], ["papers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_papers_doi"), "papers", ["doi"], unique=False)
    op.create_index(op.f("ix_papers_is_duplicate_of"), "papers", ["is_duplicate_of"], unique=False)
    op.create_index(op.f("ix_papers_pipeline_stage"), "papers", ["pipeline_stage"], unique=False)
    op.create_index(op.f("ix_papers_posted_date"), "papers", ["posted_date"], unique=False)
    op.create_index(op.f("ix_papers_review_status"), "papers", ["review_status"], unique=False)
    op.create_index(op.f("ix_papers_risk_tier"), "papers", ["risk_tier"], unique=False)

    # --- paper_groups table ---
    op.create_table(
        "paper_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column(
            "relationship",
            sa.Enum(
                "duplicate",
                "published_version",
                "updated_version",
                "cross_posted",
                name="dedup_relationship",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("strategy_used", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["canonical_id"], ["papers.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_id", "member_id", name="uq_paper_group_pair"),
    )
    op.create_index(
        op.f("ix_paper_groups_canonical_id"), "paper_groups", ["canonical_id"], unique=False
    )
    op.create_index(op.f("ix_paper_groups_member_id"), "paper_groups", ["member_id"], unique=False)

    # --- assessment_logs table ---
    op.create_table(
        "assessment_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("model_used", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=False),
        sa.Column("parsed_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_estimate_usd", sa.Float(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_assessment_logs_created_at"), "assessment_logs", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_assessment_logs_paper_id"), "assessment_logs", ["paper_id"], unique=False
    )
    op.create_index(op.f("ix_assessment_logs_stage"), "assessment_logs", ["stage"], unique=False)

    # GIN trigram index for fuzzy title search (dedup + dashboard)
    op.execute("CREATE INDEX ix_papers_title_trgm ON papers USING gin (title gin_trgm_ops)")
    # GIN tsvector index for full-text search on title + abstract
    op.execute(
        "CREATE INDEX ix_papers_tsv ON papers USING gin ("
        "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, ''))"
        ")"
    )


def downgrade() -> None:
    """Drop all tables, indexes, enums, and extensions."""

    op.execute("DROP INDEX IF EXISTS ix_papers_tsv")
    op.execute("DROP INDEX IF EXISTS ix_papers_title_trgm")

    op.drop_index(op.f("ix_assessment_logs_stage"), table_name="assessment_logs")
    op.drop_index(op.f("ix_assessment_logs_paper_id"), table_name="assessment_logs")
    op.drop_index(op.f("ix_assessment_logs_created_at"), table_name="assessment_logs")
    op.drop_table("assessment_logs")

    op.drop_index(op.f("ix_paper_groups_member_id"), table_name="paper_groups")
    op.drop_index(op.f("ix_paper_groups_canonical_id"), table_name="paper_groups")
    op.drop_table("paper_groups")

    op.drop_index(op.f("ix_papers_risk_tier"), table_name="papers")
    op.drop_index(op.f("ix_papers_review_status"), table_name="papers")
    op.drop_index(op.f("ix_papers_posted_date"), table_name="papers")
    op.drop_index(op.f("ix_papers_pipeline_stage"), table_name="papers")
    op.drop_index(op.f("ix_papers_is_duplicate_of"), table_name="papers")
    op.drop_index(op.f("ix_papers_doi"), table_name="papers")
    op.drop_table("papers")

    # Drop enums created by SQLAlchemy
    op.execute("DROP TYPE IF EXISTS review_status")
    op.execute("DROP TYPE IF EXISTS recommended_action")
    op.execute("DROP TYPE IF EXISTS risk_tier")
    op.execute("DROP TYPE IF EXISTS pipeline_stage")
    op.execute("DROP TYPE IF EXISTS source_server")
    op.execute("DROP TYPE IF EXISTS dedup_relationship")

    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
