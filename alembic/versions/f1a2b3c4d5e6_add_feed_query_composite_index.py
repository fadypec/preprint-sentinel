"""add feed query composite index

Revision ID: f1a2b3c4d5e6
Revises: d4e5f6a7b8c9
Create Date: 2026-04-19 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_papers_feed_query",
        "papers",
        ["coarse_filter_passed", "is_duplicate_of", "risk_tier", "posted_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_papers_feed_query", table_name="papers")
