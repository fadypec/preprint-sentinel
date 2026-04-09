"""add cascade deletes to FKs and language column index

Revision ID: d4e5f6a7b8c9
Revises: c3f8a1b9d402
Create Date: 2026-04-09 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3f8a1b9d402"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add index on language column (used in non-English paper queries)
    op.create_index("ix_papers_language", "papers", ["language"])

    # Update FK on assessment_logs.paper_id to CASCADE on delete
    op.drop_constraint(
        "assessment_logs_paper_id_fkey", "assessment_logs", type_="foreignkey"
    )
    op.create_foreign_key(
        "assessment_logs_paper_id_fkey",
        "assessment_logs",
        "papers",
        ["paper_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Update FK on paper_groups.canonical_id to CASCADE on delete
    op.drop_constraint(
        "paper_groups_canonical_id_fkey", "paper_groups", type_="foreignkey"
    )
    op.create_foreign_key(
        "paper_groups_canonical_id_fkey",
        "paper_groups",
        "papers",
        ["canonical_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Update FK on paper_groups.member_id to CASCADE on delete
    op.drop_constraint(
        "paper_groups_member_id_fkey", "paper_groups", type_="foreignkey"
    )
    op.create_foreign_key(
        "paper_groups_member_id_fkey",
        "paper_groups",
        "papers",
        ["member_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Revert paper_groups.member_id FK
    op.drop_constraint(
        "paper_groups_member_id_fkey", "paper_groups", type_="foreignkey"
    )
    op.create_foreign_key(
        "paper_groups_member_id_fkey",
        "paper_groups",
        "papers",
        ["member_id"],
        ["id"],
    )

    # Revert paper_groups.canonical_id FK
    op.drop_constraint(
        "paper_groups_canonical_id_fkey", "paper_groups", type_="foreignkey"
    )
    op.create_foreign_key(
        "paper_groups_canonical_id_fkey",
        "paper_groups",
        "papers",
        ["canonical_id"],
        ["id"],
    )

    # Revert assessment_logs.paper_id FK
    op.drop_constraint(
        "assessment_logs_paper_id_fkey", "assessment_logs", type_="foreignkey"
    )
    op.create_foreign_key(
        "assessment_logs_paper_id_fkey",
        "assessment_logs",
        "papers",
        ["paper_id"],
        ["id"],
    )

    # Remove language index
    op.drop_index("ix_papers_language", table_name="papers")
