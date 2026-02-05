"""make_conversation_id_nullable

Revision ID: f205b3c04a16
Revises: d8df5a9312c8
Create Date: 2026-02-05 21:24:23.639970

"""

from typing import Sequence  # noqa: UP035

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f205b3c04a16"
down_revision: str | None = "d8df5a9312c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("generations", "conversation_id", nullable=True)


def downgrade() -> None:
    op.alter_column("generations", "conversation_id", nullable=False)
