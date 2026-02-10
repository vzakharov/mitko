"""add admin_thread_id to conversations

Revision ID: a1c3e5d7f028
Revises: b57860ec7506
Create Date: 2026-02-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c3e5d7f028"
down_revision: str | None = "b57860ec7506"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("admin_thread_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "admin_thread_id")
