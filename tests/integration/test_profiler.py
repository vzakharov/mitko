"""Test ProfileService — profile creation, updates, and embedding logic.

Key behaviors:
- New profile: embedding generated, state → "ready"
- Update with same matching_summary: NO embedding regeneration
- Update with changed matching_summary: embedding regenerated
- Reset: all fields nulled, state → "onboarding"
"""

from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from mitko.models.chat import Chat
from mitko.models.user import CURRENT_PROFILER_VERSION, User
from mitko.services.profiler import ProfileService
from mitko.types.messages import ProfileData

MOCK_EMBEDDING = [0.1] * 1536


def _make_profile(**overrides: object) -> ProfileData:
    defaults = {
        "is_seeker": True,
        "is_provider": False,
        "matching_summary": "Python developer looking for backend roles",
        "practical_context": "Based in Berlin, available immediately",
    }
    return ProfileData(**(defaults | overrides))  # type: ignore[arg-type]


@patch("mitko.services.profiler.get_embedding", new_callable=AsyncMock)
async def test_create_profile_generates_embedding(
    mock_embedding: AsyncMock, db_session: AsyncSession
):
    """New profile triggers embedding generation and sets state to 'ready'."""
    mock_embedding.return_value = MOCK_EMBEDDING
    user = User(telegram_id=1001)
    db_session.add(user)
    await db_session.flush()

    result = await ProfileService(db_session).create_or_update_profile(
        user, _make_profile()
    )

    mock_embedding.assert_called_once()
    assert result.state == "ready"
    assert result.is_seeker is True
    assert result.profiler_version == CURRENT_PROFILER_VERSION
    assert result.profile_updated_at is not None


@patch("mitko.services.profiler.get_embedding", new_callable=AsyncMock)
async def test_update_same_summary_skips_embedding(
    mock_embedding: AsyncMock, db_session: AsyncSession
):
    """Update with unchanged matching_summary does NOT regenerate embedding."""
    mock_embedding.return_value = MOCK_EMBEDDING
    summary = "Python developer looking for backend roles"

    user = User(telegram_id=2001, matching_summary=summary, state="active")
    db_session.add(user)
    await db_session.flush()

    await ProfileService(db_session).create_or_update_profile(
        user, _make_profile(matching_summary=summary), is_update=True
    )

    mock_embedding.assert_not_called()


@patch("mitko.services.profiler.get_embedding", new_callable=AsyncMock)
async def test_update_changed_summary_regenerates_embedding(
    mock_embedding: AsyncMock, db_session: AsyncSession
):
    """Update with changed matching_summary triggers new embedding."""
    mock_embedding.return_value = MOCK_EMBEDDING

    user = User(
        telegram_id=3001,
        matching_summary="Old summary",
        state="active",
    )
    db_session.add(user)
    await db_session.flush()

    await ProfileService(db_session).create_or_update_profile(
        user, _make_profile(matching_summary="New summary"), is_update=True
    )

    mock_embedding.assert_called_once_with("New summary")


@patch("mitko.services.profiler.get_embedding", new_callable=AsyncMock)
async def test_update_sets_state_to_updated(
    mock_embedding: AsyncMock, db_session: AsyncSession
):
    """Profile update sets state to 'updated' (not 'ready')."""
    mock_embedding.return_value = MOCK_EMBEDDING

    user = User(telegram_id=4001, matching_summary="Old", state="active")
    db_session.add(user)
    await db_session.flush()

    result = await ProfileService(db_session).create_or_update_profile(
        user, _make_profile(), is_update=True
    )

    assert result.state == "updated"


@patch("mitko.services.profiler.get_embedding", new_callable=AsyncMock)
async def test_activate_profile(
    mock_embedding: AsyncMock, db_session: AsyncSession
):
    """Activation sets state to 'active'."""
    mock_embedding.return_value = MOCK_EMBEDDING
    user = User(telegram_id=5001, state="ready")
    db_session.add(user)
    await db_session.flush()

    result = await ProfileService(db_session).activate_profile(user)
    assert result.state == "active"


async def test_reset_profile(db_session: AsyncSession):
    """Reset clears all profile fields and chat history."""
    user = User(
        telegram_id=6001,
        is_seeker=True,
        matching_summary="some summary",
        embedding=[0.1] * 1536,
        state="active",
    )
    chat = Chat(
        telegram_id=6001,
        message_history=[{"role": "user", "content": "hello"}],
        user_prompt="test",
    )
    db_session.add(user)
    db_session.add(chat)
    await db_session.flush()

    await ProfileService(db_session).reset_profile(user, chat)

    assert user.state == "onboarding"
    assert user.is_seeker is None
    assert user.matching_summary is None
    assert user.embedding is None
    assert user.profiler_version is None
    assert user.profile_updated_at is None
    assert chat.message_history == []
    assert chat.user_prompt is None
