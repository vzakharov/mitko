"""rename thread_id to source_message_id in announces

Revision ID: 13e2be4e1b7c
Revises: 2b69efc08e25
Create Date: 2026-02-18 01:23:47.681094

"""

from typing import Sequence  # noqa: UP035

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "13e2be4e1b7c"
down_revision: str | None = "2b69efc08e25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("announces_thread_id_key", "announces", type_="unique")
    op.alter_column(
        "announces", "thread_id", new_column_name="source_message_id"
    )
    op.create_unique_constraint(
        "announces_source_message_id_key", "announces", ["source_message_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "announces_source_message_id_key", "announces", type_="unique"
    )
    op.alter_column(
        "announces", "source_message_id", new_column_name="thread_id"
    )
    op.create_unique_constraint(
        "announces_thread_id_key", "announces", ["thread_id"]
    )
