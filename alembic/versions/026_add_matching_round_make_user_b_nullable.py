"""add matching round and make user_b_id nullable

Revision ID: 5b1091d18e36
Revises: 010faae6c735
Create Date: 2026-02-06 12:38:54.051353

"""

from typing import Sequence  # noqa: UP035

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b1091d18e36"
down_revision: str | None = "010faae6c735"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column(
            "matching_round", sa.Integer(), server_default="1", nullable=False
        ),
    )
    op.alter_column(
        "matches", "user_b_id", existing_type=sa.BIGINT(), nullable=True
    )
    op.create_index(
        "ix_matches_matching_round", "matches", ["matching_round"], unique=False
    )
    op.alter_column(
        "users", "profile_version", new_column_name="profiler_version"
    )


def downgrade() -> None:
    op.alter_column(
        "users", "profiler_version", new_column_name="profile_version"
    )
    op.drop_index("ix_matches_matching_round", table_name="matches")
    op.alter_column(
        "matches", "user_b_id", existing_type=sa.BIGINT(), nullable=False
    )
    op.drop_column("matches", "matching_round")
