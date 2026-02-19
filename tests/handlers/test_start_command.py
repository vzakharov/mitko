"""Test /start command handler.

Key behaviors:
- New user: greeting sent, User + Chat created with empty history
- Existing user with data: reset warning with confirmation keyboard
"""

from aiogram.methods import SendMessage
from sqlalchemy.ext.asyncio import AsyncSession

from mitko.bot.handlers import cmd_start
from mitko.db import get_or_create_chat, get_or_create_user
from mitko.i18n import L

from .helpers import make_bot, make_message, patch_get_db


async def test_new_user_gets_greeting(db_session: AsyncSession):
    """Brand-new user receives greeting and gets empty chat state."""
    bot = make_bot()
    msg = make_message(bot, user_id=5001)

    async with patch_get_db(db_session):
        await cmd_start(msg)

    req = bot.get_request()
    assert isinstance(req, SendMessage)
    assert req.text == L.commands.start.GREETING

    chat = await get_or_create_chat(db_session, 5001)
    assert chat.message_history == []
    assert chat.user_prompt is None


async def test_existing_user_with_summary_gets_reset_warning(
    db_session: AsyncSession,
):
    """User who already has a matching_summary sees the reset confirmation."""
    user = await get_or_create_user(db_session, 5002)
    await get_or_create_chat(db_session, 5002)
    user.matching_summary = "Senior Python dev"
    await db_session.flush()

    bot = make_bot()
    msg = make_message(bot, user_id=5002)

    async with patch_get_db(db_session):
        await cmd_start(msg)

    req = bot.get_request()
    assert isinstance(req, SendMessage)
    assert req.text == L.commands.reset.WARNING
    assert req.reply_markup is not None


async def test_existing_user_with_role_gets_reset_warning(
    db_session: AsyncSession,
):
    """User who has role set (but no summary) still sees reset warning."""
    user = await get_or_create_user(db_session, 5003)
    await get_or_create_chat(db_session, 5003)
    user.is_seeker = True
    await db_session.flush()

    bot = make_bot()
    msg = make_message(bot, user_id=5003)

    async with patch_get_db(db_session):
        await cmd_start(msg)

    req = bot.get_request()
    assert isinstance(req, SendMessage)
    assert req.text == L.commands.reset.WARNING


async def test_existing_user_with_chat_history_gets_reset_warning(
    db_session: AsyncSession,
):
    """User with non-empty chat history sees reset warning."""
    await get_or_create_user(db_session, 5004)
    chat = await get_or_create_chat(db_session, 5004)
    chat.message_history = [{"role": "user", "content": "hi"}]
    await db_session.flush()

    bot = make_bot()
    msg = make_message(bot, user_id=5004)

    async with patch_get_db(db_session):
        await cmd_start(msg)

    req = bot.get_request()
    assert isinstance(req, SendMessage)
    assert req.text == L.commands.reset.WARNING


async def test_existing_user_with_pending_prompt_gets_reset_warning(
    db_session: AsyncSession,
):
    """User with user_prompt pending sees reset warning."""
    await get_or_create_user(db_session, 5005)
    chat = await get_or_create_chat(db_session, 5005)
    chat.user_prompt = "I'm looking for a job"
    await db_session.flush()

    bot = make_bot()
    msg = make_message(bot, user_id=5005)

    async with patch_get_db(db_session):
        await cmd_start(msg)

    req = bot.get_request()
    assert isinstance(req, SendMessage)
    assert req.text == L.commands.reset.WARNING
