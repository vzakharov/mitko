"""Test match accept/reject callback handlers.

Key behaviors:
- User A accepts first (qualified → a_accepted)
- User B accepts first (qualified → b_accepted)
- Second user accepts (→ connected, both notified)
- User rejects (→ rejected)
"""

from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from mitko.bot.handlers import handle_match_accept, handle_match_reject
from mitko.bot.keyboards import MatchAction
from mitko.db import get_or_create_user
from mitko.i18n import L
from mitko.models.match import Match, MatchStatus

from .helpers import make_callback, patch_get_db

USER_A_TG = 6001
USER_B_TG = 6002


async def _setup_match(
    session: AsyncSession,
    *,
    status: MatchStatus = "qualified",
) -> Match:
    """Create two users and a match between them."""
    user_a = await get_or_create_user(session, USER_A_TG)
    user_a.matching_summary = "Backend developer"
    user_b = await get_or_create_user(session, USER_B_TG)
    user_b.matching_summary = "CTO hiring backend"
    match = Match(
        user_a_id=USER_A_TG,
        user_b_id=USER_B_TG,
        similarity_score=0.9,
        match_rationale="Great fit",
        status=status,
    )
    session.add(match)
    await session.flush()
    return match


async def test_user_a_accepts_first(db_session: AsyncSession):
    """When user_a accepts a qualified match, status becomes a_accepted."""
    match = await _setup_match(db_session)
    fake = make_callback(
        MatchAction(action="accept", match_id=str(match.id)).pack(),
        user_id=USER_A_TG,
    )

    async with patch_get_db(db_session):
        await handle_match_accept(
            fake.callback,
            MatchAction(action="accept", match_id=str(match.id)),
        )

    assert match.status == "a_accepted"
    fake.answer.assert_called_once_with(L.matching.ACCEPT_WAITING)


async def test_user_b_accepts_first(db_session: AsyncSession):
    """When user_b accepts a qualified match, status becomes b_accepted."""
    match = await _setup_match(db_session)
    fake = make_callback(
        MatchAction(action="accept", match_id=str(match.id)).pack(),
        user_id=USER_B_TG,
    )

    async with patch_get_db(db_session):
        await handle_match_accept(
            fake.callback,
            MatchAction(action="accept", match_id=str(match.id)),
        )

    assert match.status == "b_accepted"
    fake.answer.assert_called_once_with(L.matching.ACCEPT_WAITING)


@patch("mitko.bot.handlers.send_to_user", new_callable=AsyncMock)
@patch("mitko.bot.handlers.get_bot")
async def test_both_accept_becomes_connected(
    mock_get_bot: AsyncMock,
    mock_send: AsyncMock,
    db_session: AsyncSession,
):
    """When second user accepts, status → connected and both are notified."""
    mock_get_bot.return_value = AsyncMock()
    match = await _setup_match(db_session, status="a_accepted")

    fake = make_callback(
        MatchAction(action="accept", match_id=str(match.id)).pack(),
        user_id=USER_B_TG,
    )

    async with patch_get_db(db_session):
        await handle_match_accept(
            fake.callback,
            MatchAction(action="accept", match_id=str(match.id)),
        )

    assert match.status == "connected"
    # Callback user gets notified via callback.answer
    fake.answer.assert_called_once()
    # Other user gets notified via send_to_user
    mock_send.assert_called_once()
    assert mock_send.call_args[0][1] == USER_A_TG


@patch("mitko.bot.handlers.send_to_user", new_callable=AsyncMock)
@patch("mitko.bot.handlers.get_bot")
async def test_user_a_completes_b_accepted_match(
    mock_get_bot: AsyncMock,
    mock_send: AsyncMock,
    db_session: AsyncSession,
):
    """When user_a accepts a b_accepted match, status → connected."""
    mock_get_bot.return_value = AsyncMock()
    match = await _setup_match(db_session, status="b_accepted")

    fake = make_callback(
        MatchAction(action="accept", match_id=str(match.id)).pack(),
        user_id=USER_A_TG,
    )

    async with patch_get_db(db_session):
        await handle_match_accept(
            fake.callback,
            MatchAction(action="accept", match_id=str(match.id)),
        )

    assert match.status == "connected"
    fake.answer.assert_called_once()
    mock_send.assert_called_once()
    assert mock_send.call_args[0][1] == USER_B_TG


async def test_reject_sets_rejected(db_session: AsyncSession):
    """Rejecting a match sets status to rejected."""
    match = await _setup_match(db_session)
    fake = make_callback(
        MatchAction(action="reject", match_id=str(match.id)).pack(),
        user_id=USER_A_TG,
    )

    async with patch_get_db(db_session):
        await handle_match_reject(
            fake.callback,
            MatchAction(action="reject", match_id=str(match.id)),
        )

    assert match.status == "rejected"
    fake.answer.assert_called_once_with(L.matching.REJECT_NOTED)
