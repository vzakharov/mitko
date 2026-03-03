"""Unit tests for mirror_to_admin_thread in admin_group service."""

from unittest.mock import MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from mitko.models.user import User


async def _create_user(session: AsyncSession, telegram_id: int) -> User:
    user = User(telegram_id=telegram_id, state="active")
    session.add(user)
    await session.flush()
    return user


async def test_mirror_logs_exception_when_no_chat(db_session: AsyncSession):
    """mirror_to_admin_thread logs an exception and does not raise when no Chat row exists."""
    from mitko.services.admin_group import mirror_to_admin_thread

    await _create_user(db_session, 9001)
    # Intentionally no Chat row created

    with patch("mitko.services.admin_group.logger") as mock_logger:
        await mirror_to_admin_thread(
            MagicMock(), 9001, "test message", db_session
        )

    mock_logger.exception.assert_called_once()
    assert "9001" in str(mock_logger.exception.call_args)
