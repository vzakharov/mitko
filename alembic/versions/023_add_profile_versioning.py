"""add profile versioning

Revision ID: d8df5a9312c8
Revises: 19820eea78c3
Create Date: 2026-02-05 15:26:56.967582

"""

from typing import Sequence  # noqa: UP035

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8df5a9312c8"
down_revision: str | None = "19820eea78c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("profile_version", sa.Integer(), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "profile_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
    )

    op.execute(
        text("""
        UPDATE users
        SET
            profile_version = 1,
            profile_updated_at = created_at
        WHERE is_complete = true
    """)
    )


def downgrade() -> None:
    op.execute(
        text("""
        UPDATE users
        SET
            profile_version = NULL,
            profile_updated_at = NULL
        WHERE profile_version = 1
    """)
    )

    op.drop_column("users", "profile_updated_at")
    op.drop_column("users", "profile_version")
