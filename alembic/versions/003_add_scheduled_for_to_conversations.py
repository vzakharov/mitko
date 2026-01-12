"""Add scheduled_for column to conversations for generation queue"""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_scheduled_for"
down_revision: str | None = "002_merge_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index for efficient "find next scheduled" query
    op.create_index(
        "ix_conversations_scheduled_for",
        "conversations",
        ["scheduled_for"],
        postgresql_where=sa.text("scheduled_for IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_scheduled_for", table_name="conversations")
    op.drop_column("conversations", "scheduled_for")
