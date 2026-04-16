"""sync missing columns, tables, and indexes

Brings Alembic in line with the Prisma schema and SQLAlchemy models.
Several columns and tables were added via `prisma db push` during
development but never received Alembic migrations.  This migration
uses IF NOT EXISTS / IF EXISTS guards so it is safe to run on databases
where `prisma db push` was already applied.

Missing pieces added:
- papers: coarse_filter_passed, needs_manual_review, enrichment_data
- pipeline_runs table
- accounts table (NextAuth)
- sessions table (NextAuth)
- users: status, email_verified columns
- user_status enum

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-04-16 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add missing columns, tables, and indexes to match Prisma schema."""

    # ── papers: missing columns ──────────────────────────────────────
    op.execute(
        "ALTER TABLE papers ADD COLUMN IF NOT EXISTS "
        "coarse_filter_passed boolean"
    )
    op.execute(
        "ALTER TABLE papers ADD COLUMN IF NOT EXISTS "
        "needs_manual_review boolean NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE papers ADD COLUMN IF NOT EXISTS "
        "enrichment_data jsonb"
    )

    # Indexes (IF NOT EXISTS is not standard for CREATE INDEX,
    # so wrap in a DO block)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_indexes
                           WHERE indexname = 'papers_coarse_filter_passed_idx') THEN
                CREATE INDEX "papers_coarse_filter_passed_idx"
                    ON papers (coarse_filter_passed);
            END IF;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_indexes
                           WHERE indexname = 'papers_needs_manual_review_idx') THEN
                CREATE INDEX "papers_needs_manual_review_idx"
                    ON papers (needs_manual_review);
            END IF;
        END $$
    """)

    # ── pipeline_runs table ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            started_at  timestamptz NOT NULL,
            finished_at timestamptz,
            papers_ingested          int NOT NULL DEFAULT 0,
            papers_after_dedup       int NOT NULL DEFAULT 0,
            papers_coarse_passed     int NOT NULL DEFAULT 0,
            papers_fulltext_retrieved int NOT NULL DEFAULT 0,
            papers_methods_analysed  int NOT NULL DEFAULT 0,
            papers_enriched          int NOT NULL DEFAULT 0,
            papers_adjudicated       int NOT NULL DEFAULT 0,
            current_stage  varchar(50),
            pubmed_query_mode varchar(20),
            pid            int,
            from_date      date,
            to_date        date,
            errors         jsonb,
            total_cost_usd float8 NOT NULL DEFAULT 0,
            trigger        varchar(50) NOT NULL,
            backlog_stats  jsonb
        )
    """)

    # ── users: missing columns ───────────────────────────────────────
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE user_status AS ENUM ('pending','approved','rejected'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "status user_status NOT NULL DEFAULT 'pending'"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "email_verified timestamptz"
    )

    # ── accounts table (NextAuth) ────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type                text NOT NULL,
            provider            text NOT NULL,
            provider_account_id text NOT NULL,
            refresh_token       text,
            access_token        text,
            expires_at          int,
            token_type          text,
            scope               text,
            id_token            text,
            UNIQUE (provider, provider_account_id)
        )
    """)

    # ── sessions table (NextAuth) ────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            session_token text NOT NULL UNIQUE,
            user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires       timestamptz NOT NULL
        )
    """)

    # ── search_vector (idempotent, also in migration 0dafeb7c9b81) ──
    # Ensures the generated column exists even if only Prisma was used
    # to set up the database initially.
    op.execute("""
        ALTER TABLE papers ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(abstract, '')), 'B')
        ) STORED
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_papers_search "
        "ON papers USING GIN(search_vector)"
    )


def downgrade() -> None:
    """Remove additions (reverse order)."""
    op.execute("DROP INDEX IF EXISTS idx_papers_search")
    op.execute("ALTER TABLE papers DROP COLUMN IF EXISTS search_vector")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS accounts")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email_verified")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS status")
    op.execute("DROP TYPE IF EXISTS user_status")
    op.execute("DROP TABLE IF EXISTS pipeline_runs")
    op.execute("DROP INDEX IF EXISTS papers_needs_manual_review_idx")
    op.execute("DROP INDEX IF EXISTS papers_coarse_filter_passed_idx")
    op.execute("ALTER TABLE papers DROP COLUMN IF EXISTS enrichment_data")
    op.execute("ALTER TABLE papers DROP COLUMN IF EXISTS needs_manual_review")
    op.execute("ALTER TABLE papers DROP COLUMN IF EXISTS coarse_filter_passed")
