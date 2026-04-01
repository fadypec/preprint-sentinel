"""add composite index posted_date + pipeline_stage

Revision ID: c3f8a1b9d402
Revises: 0dafeb7c9b81
Create Date: 2026-04-01 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f8a1b9d402"
down_revision: str | None = "0dafeb7c9b81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_papers_posted_date_stage",
        "papers",
        ["posted_date", "pipeline_stage"],
    )


def downgrade() -> None:
    op.drop_index("ix_papers_posted_date_stage", table_name="papers")
