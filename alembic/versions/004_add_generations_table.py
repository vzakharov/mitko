"""Add generations table and remove scheduled_for from conversations"""

from typing import Sequence  # noqa: UP035

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_add_generations"
down_revision: str | None = "003_add_scheduled_for"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create generations table
    op.create_table(
        "generations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_generations_conversation_id",
        "generations",
        ["conversation_id"],
    )
    op.create_index(
        "ix_generations_scheduled_for",
        "generations",
        ["scheduled_for"],
    )
    op.create_index(
        "ix_generations_status",
        "generations",
        ["status"],
    )

    # Remove scheduled_for from conversations
    op.drop_index(
        "ix_conversations_scheduled_for",
        table_name="conversations",
    )
    op.drop_column("conversations", "scheduled_for")


def downgrade() -> None:
    # Re-add scheduled_for to conversations
    op.add_column(
        "conversations",
        sa.Column(
            "scheduled_for",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_conversations_scheduled_for",
        "conversations",
        ["scheduled_for"],
        postgresql_where=sa.text("scheduled_for IS NOT NULL"),
    )

    # Drop generations table
    op.drop_index("ix_generations_status", table_name="generations")
    op.drop_index("ix_generations_scheduled_for", table_name="generations")
    op.drop_index("ix_generations_conversation_id", table_name="generations")
    op.drop_table("generations")
