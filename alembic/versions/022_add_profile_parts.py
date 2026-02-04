"""add profile parts

Revision ID: 19820eea78c3
Revises: 432253f512f4
Create Date: 2026-02-04 21:54:21.531965

"""

from typing import Sequence  # noqa: UP035

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "19820eea78c3"
down_revision: str | None = "432253f512f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Rename summary → matching_summary (keeps existing data and embeddings)
    op.alter_column("users", "summary", new_column_name="matching_summary")

    # Add new columns (nullable, will be populated via lazy regeneration)
    op.add_column(
        "users", sa.Column("practical_context", sa.Text(), nullable=True)
    )
    op.add_column(
        "users", sa.Column("private_observations", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "private_observations")
    op.drop_column("users", "practical_context")
    op.alter_column("users", "matching_summary", new_column_name="summary")
