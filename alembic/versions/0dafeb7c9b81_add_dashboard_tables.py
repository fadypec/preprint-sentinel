"""add dashboard tables

Revision ID: 0dafeb7c9b81
Revises: a0314de3b571
Create Date: 2026-03-31 10:53:31.153636

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0dafeb7c9b81"
down_revision: str | Sequence[str] | None = "a0314de3b571"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create users and pipeline_settings tables; add search_vector to papers."""

    # --- users table ---
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("image", sa.Text(), nullable=True),
        sa.Column(
            "role",
            sa.Enum(
                "admin",
                "analyst",
                name="user_role",
                create_constraint=True,
            ),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)

    # --- pipeline_settings table ---
    op.create_table(
        "pipeline_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Full-text search index on papers
    op.execute("""
        ALTER TABLE papers ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(abstract, '')), 'B')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_papers_search ON papers USING GIN(search_vector)
    """)


def downgrade() -> None:
    """Drop users and pipeline_settings tables; remove search_vector from papers."""

    op.execute("DROP INDEX IF EXISTS idx_papers_search")
    op.execute("ALTER TABLE papers DROP COLUMN IF EXISTS search_vector")

    op.drop_table("pipeline_settings")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS user_role")
