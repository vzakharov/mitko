"""Merge Profile into User model with multi-role support"""

from typing import Sequence  # noqa: UP035

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_merge_profile"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add profile fields to users table
    op.add_column("users", sa.Column("is_seeker", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("is_provider", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("structured_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("users", sa.Column("embedding", Vector(1536), nullable=True))
    op.add_column(
        "users", sa.Column("is_complete", sa.Boolean(), server_default="false", nullable=False)
    )

    # Migrate data from profiles to users
    op.execute(
        """
        UPDATE users u
        SET
            is_seeker = CASE WHEN p.role = 'seeker' THEN true ELSE false END,
            is_provider = CASE WHEN p.role = 'provider' THEN true ELSE false END,
            summary = p.summary,
            structured_data = p.structured_data,
            embedding = p.embedding,
            is_complete = p.is_complete
        FROM profiles p
        WHERE u.telegram_id = p.telegram_id
    """
    )

    # Update matches table to reference users instead of profiles
    op.add_column("matches", sa.Column("user_a_id", sa.BigInteger(), nullable=True))
    op.add_column("matches", sa.Column("user_b_id", sa.BigInteger(), nullable=True))

    # Migrate match references from profile IDs to user telegram_ids
    op.execute(
        """
        UPDATE matches m
        SET
            user_a_id = (SELECT telegram_id FROM profiles WHERE id = m.profile_a_id),
            user_b_id = (SELECT telegram_id FROM profiles WHERE id = m.profile_b_id)
    """
    )

    # Make new columns non-nullable
    op.alter_column("matches", "user_a_id", nullable=False)
    op.alter_column("matches", "user_b_id", nullable=False)

    # Add foreign keys for new columns
    op.create_foreign_key(
        "matches_user_a_id_fkey", "matches", "users", ["user_a_id"], ["telegram_id"]
    )
    op.create_foreign_key(
        "matches_user_b_id_fkey", "matches", "users", ["user_b_id"], ["telegram_id"]
    )

    # Add index on embedding for vector search
    op.create_index(
        "ix_users_embedding",
        "users",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # Drop old foreign keys and columns from matches
    op.drop_constraint("matches_profile_a_id_fkey", "matches", type_="foreignkey")
    op.drop_constraint("matches_profile_b_id_fkey", "matches", type_="foreignkey")
    op.drop_column("matches", "profile_a_id")
    op.drop_column("matches", "profile_b_id")

    # Drop old role column from users (replaced by is_seeker/is_provider)
    op.drop_column("users", "role")

    # Drop profiles table entirely
    op.drop_index("ix_profiles_embedding", table_name="profiles")
    op.drop_table("profiles")


def downgrade() -> None:
    # Recreate profiles table
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("structured_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("is_complete", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["telegram_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index(
        "ix_profiles_embedding",
        "profiles",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # Migrate data back from users to profiles
    op.execute(
        """
        INSERT INTO profiles (id, telegram_id, role, summary, structured_data, embedding, is_complete)
        SELECT
            gen_random_uuid(),
            telegram_id,
            CASE WHEN is_seeker = true THEN 'seeker' ELSE 'provider' END,
            COALESCE(summary, ''),
            COALESCE(structured_data, '{}'::jsonb),
            embedding,
            is_complete
        FROM users
        WHERE is_complete = true
    """
    )

    # Restore old matches columns
    op.add_column(
        "matches", sa.Column("profile_a_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "matches", sa.Column("profile_b_id", postgresql.UUID(as_uuid=True), nullable=True)
    )

    # Migrate match references back
    op.execute(
        """
        UPDATE matches m
        SET
            profile_a_id = (SELECT id FROM profiles WHERE telegram_id = m.user_a_id),
            profile_b_id = (SELECT id FROM profiles WHERE telegram_id = m.user_b_id)
    """
    )

    # Make columns non-nullable
    op.alter_column("matches", "profile_a_id", nullable=False)
    op.alter_column("matches", "profile_b_id", nullable=False)

    # Restore foreign keys
    op.create_foreign_key(
        "matches_profile_a_id_fkey", "matches", "profiles", ["profile_a_id"], ["id"]
    )
    op.create_foreign_key(
        "matches_profile_b_id_fkey", "matches", "profiles", ["profile_b_id"], ["id"]
    )

    # Drop new columns
    op.drop_constraint("matches_user_a_id_fkey", "matches", type_="foreignkey")
    op.drop_constraint("matches_user_b_id_fkey", "matches", type_="foreignkey")
    op.drop_column("matches", "user_b_id")
    op.drop_column("matches", "user_a_id")

    # Restore role column to users
    op.add_column("users", sa.Column("role", sa.String(length=20), nullable=True))
    op.execute(
        """
        UPDATE users
        SET role = CASE WHEN is_seeker = true THEN 'seeker' ELSE 'provider' END
        WHERE is_complete = true
    """
    )

    # Drop profile fields from users
    op.drop_index("ix_users_embedding", table_name="users")
    op.drop_column("users", "is_complete")
    op.drop_column("users", "embedding")
    op.drop_column("users", "structured_data")
    op.drop_column("users", "summary")
    op.drop_column("users", "is_provider")
    op.drop_column("users", "is_seeker")
