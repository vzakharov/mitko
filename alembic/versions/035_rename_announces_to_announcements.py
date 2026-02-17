"""rename announces table to announcements

Revision ID: a3f7c2d15e89
Revises: 13e2be4e1b7c
Create Date: 2026-02-18 12:00:00.000000

"""

from typing import Sequence  # noqa: UP035

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f7c2d15e89"
down_revision: str | None = "13e2be4e1b7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE announces RENAME TO announcements")
    op.execute("ALTER INDEX announces_pkey RENAME TO announcements_pkey")
    op.execute(
        "ALTER INDEX announces_group_id_key RENAME TO announcements_group_id_key"
    )
    op.execute(
        "ALTER INDEX announces_source_message_id_key RENAME TO announcements_source_message_id_key"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE announcements RENAME TO announces")
    op.execute("ALTER INDEX announcements_pkey RENAME TO announces_pkey")
    op.execute(
        "ALTER INDEX announcements_group_id_key RENAME TO announces_group_id_key"
    )
    op.execute(
        "ALTER INDEX announcements_source_message_id_key RENAME TO announces_source_message_id_key"
    )
