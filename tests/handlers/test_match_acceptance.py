"""Test match accept/reject callback handlers.

Key behaviors:
- User A accepts first (qualified → a_accepted)
- User B accepts first (qualified → b_accepted)
- Second user accepts (→ connected, both notified)
- User rejects (→ rejected)
"""

from unittest.mock import AsyncMock, patch

from aiogram.methods import AnswerCallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from mitko.bot.handlers import handle_match_accept, handle_match_reject
from mitko.bot.keyboards import MatchAction
from mitko.db import get_or_create_chat, get_or_create_user
from mitko.i18n import L
from mitko.models.match import Match, MatchStatus

from .helpers import make_bot, make_callback, patch_get_db

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
    # Create chats for both users (needed for send_and_record_bot_message)
    await get_or_create_chat(session, USER_A_TG)
    await get_or_create_chat(session, USER_B_TG)
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
    bot = make_bot()
    cb = make_callback(
        bot,
        MatchAction(action="accept", match_id=str(match.id)).pack(),
        user_id=USER_A_TG,
    )

    async with patch_get_db(db_session):
        await handle_match_accept(
            cb, MatchAction(action="accept", match_id=str(match.id))
        )

    assert match.status == "a_accepted"
    req = bot.get_request()
    assert isinstance(req, AnswerCallbackQuery)
    assert req.text == L.matching.ACCEPT_WAITING


async def test_user_b_accepts_first(db_session: AsyncSession):
    """When user_b accepts a qualified match, status becomes b_accepted."""
    match = await _setup_match(db_session)
    bot = make_bot()
    cb = make_callback(
        bot,
        MatchAction(action="accept", match_id=str(match.id)).pack(),
        user_id=USER_B_TG,
    )

    async with patch_get_db(db_session):
        await handle_match_accept(
            cb, MatchAction(action="accept", match_id=str(match.id))
        )

    assert match.status == "b_accepted"
    req = bot.get_request()
    assert isinstance(req, AnswerCallbackQuery)
    assert req.text == L.matching.ACCEPT_WAITING


@patch("mitko.services.chat_utils.send_to_user", new_callable=AsyncMock)
@patch("mitko.bot.handlers.get_bot")
async def test_both_accept_becomes_connected(
    mock_get_bot: AsyncMock,
    mock_send: AsyncMock,
    db_session: AsyncSession,
):
    """When second user accepts, status → connected and both are notified.

    Note: callback.answer() goes through asyncio.gather alongside send_to_user,
    and aiogram's TelegramMethod objects are unhashable (breaks gather's dedup).
    So for the connected path we don't inject MockedBot — we only verify the
    status transition and that send_and_record_bot_message was called for both users.
    The callback.answer() path is covered by the first-accept tests above.
    """
    mock_get_bot.return_value = AsyncMock()
    match = await _setup_match(db_session, status="a_accepted")

    bot = make_bot()
    cb = make_callback(
        bot,
        MatchAction(action="accept", match_id=str(match.id)).pack(),
        user_id=USER_B_TG,
        stage_replies=0,
    )
    # Mock callback.answer to avoid gather+TelegramMethod hash conflict
    object.__setattr__(cb, "answer", AsyncMock())

    async with patch_get_db(db_session):
        await handle_match_accept(
            cb, MatchAction(action="accept", match_id=str(match.id))
        )

    assert match.status == "connected"
    # send_to_user is called twice (once for each user via send_and_record_bot_message)
    assert mock_send.call_count == 2
    # Check both users were notified (second arg is Chat object, extract telegram_id)
    call_recipients = {
        call[0][1].telegram_id for call in mock_send.call_args_list
    }
    assert call_recipients == {USER_A_TG, USER_B_TG}


@patch("mitko.services.chat_utils.send_to_user", new_callable=AsyncMock)
@patch("mitko.bot.handlers.get_bot")
async def test_user_a_completes_b_accepted_match(
    mock_get_bot: AsyncMock,
    mock_send: AsyncMock,
    db_session: AsyncSession,
):
    """When user_a accepts a b_accepted match, status → connected."""
    mock_get_bot.return_value = AsyncMock()
    match = await _setup_match(db_session, status="b_accepted")

    bot = make_bot()
    cb = make_callback(
        bot,
        MatchAction(action="accept", match_id=str(match.id)).pack(),
        user_id=USER_A_TG,
        stage_replies=0,
    )
    object.__setattr__(cb, "answer", AsyncMock())

    async with patch_get_db(db_session):
        await handle_match_accept(
            cb, MatchAction(action="accept", match_id=str(match.id))
        )

    assert match.status == "connected"
    # send_to_user is called twice (once for each user via send_and_record_bot_message)
    assert mock_send.call_count == 2
    # Check both users were notified (second arg is Chat object, extract telegram_id)
    call_recipients = {
        call[0][1].telegram_id for call in mock_send.call_args_list
    }
    assert call_recipients == {USER_A_TG, USER_B_TG}


async def test_reject_sets_rejected(db_session: AsyncSession):
    """Rejecting a match sets status to rejected."""
    match = await _setup_match(db_session)
    bot = make_bot()
    cb = make_callback(
        bot,
        MatchAction(action="reject", match_id=str(match.id)).pack(),
        user_id=USER_A_TG,
    )

    async with patch_get_db(db_session):
        await handle_match_reject(
            cb, MatchAction(action="reject", match_id=str(match.id))
        )

    assert match.status == "rejected"
    req = bot.get_request()
    assert isinstance(req, AnswerCallbackQuery)
    assert req.text == L.matching.REJECT_NOTED
