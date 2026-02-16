"""rename conversations to chats

Revision ID: b2d4f6a8c029
Revises: a1c3e5d7f028
Create Date: 2026-02-12 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b2d4f6a8c029"
down_revision: str | None = "a1c3e5d7f028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("conversations", "chats")
    op.alter_column("generations", "conversation_id", new_column_name="chat_id")
    op.execute(
        "ALTER INDEX ix_generations_conversation_id RENAME TO ix_generations_chat_id"
    )
    op.execute(
        "ALTER TABLE generations RENAME CONSTRAINT "
        "generations_conversation_id_fkey TO generations_chat_id_fkey"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE generations RENAME CONSTRAINT "
        "generations_chat_id_fkey TO generations_conversation_id_fkey"
    )
    op.execute(
        "ALTER INDEX ix_generations_chat_id RENAME TO ix_generations_conversation_id"
    )
    op.alter_column("generations", "chat_id", new_column_name="conversation_id")
    op.rename_table("chats", "conversations")
