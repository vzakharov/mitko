"""Test database fixtures work correctly."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitko.models.user import User


async def test_insert_user(db_session: AsyncSession):
    """Insert a user with commit — next test verifies it was rolled back."""
    db_session.add(User(telegram_id=12345, username="test_user"))
    await db_session.commit()

    assert len((await db_session.execute(select(User))).scalars().all()) == 1


async def test_isolation_after_insert(db_session: AsyncSession):
    """Verify previous test's data was rolled back."""
    assert (await db_session.execute(select(User))).scalars().all() == []
