"""Reusable factories for fake aiogram types used in handler tests.

Uses aiogram's own MockedBot pattern: real Message/CallbackQuery objects
with a MockedBot injected via .as_(bot).  Outgoing API calls are captured
and can be inspected via bot.get_request().
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import patch

from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Message
from aiogram.types import Chat as TgChat
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from .mocked_bot import MockedBot

# Reusable dummy Message result for staging SendMessage responses.
_DUMMY_MSG = Message(
    message_id=999,
    date=datetime.now(),
    chat=TgChat(id=1, type="private"),
)


def make_bot() -> MockedBot:
    return MockedBot()


def _stage_send_message(bot: MockedBot) -> None:
    """Pre-stage a successful SendMessage response."""
    bot.add_result_for(SendMessage, ok=True, result=_DUMMY_MSG)


def _stage_callback_answer(bot: MockedBot) -> None:
    """Pre-stage a successful AnswerCallbackQuery response."""
    bot.add_result_for(AnswerCallbackQuery, ok=True, result=True)


def make_message(
    bot: MockedBot,
    text: str = "hello",
    user_id: int = 12345,
    message_id: int = 1,
    *,
    stage_replies: int = 1,
) -> Message:
    """Create a real Message with MockedBot injected.

    Args:
        stage_replies: how many SendMessage responses to pre-stage
                       (one per expected message.answer() call).
    """
    msg = Message(
        message_id=message_id,
        date=datetime.now(),
        chat=TgChat(id=user_id, type="private"),
        from_user=TgUser(id=user_id, is_bot=False, first_name="Test"),
        text=text,
    )
    msg.as_(bot)
    for _ in range(stage_replies):
        _stage_send_message(bot)
    return msg


def make_callback(
    bot: MockedBot,
    data: str,
    user_id: int = 12345,
    message_id: int = 1,
    *,
    stage_replies: int = 1,
) -> CallbackQuery:
    """Create a real CallbackQuery with MockedBot injected.

    Args:
        stage_replies: how many AnswerCallbackQuery responses to pre-stage.
    """
    inner_msg = Message(
        message_id=message_id,
        date=datetime.now(),
        chat=TgChat(id=user_id, type="private"),
        from_user=TgUser(id=user_id, is_bot=False, first_name="Test"),
        text="original",
    )
    cb = CallbackQuery(
        id="test_cb_1",
        chat_instance="test",
        from_user=TgUser(id=user_id, is_bot=False, first_name="Test"),
        message=inner_msg,
        data=data,
    )
    cb.as_(bot)
    for _ in range(stage_replies):
        _stage_callback_answer(bot)
    return cb


@asynccontextmanager
async def patch_get_db(
    session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Context manager that patches get_db in both handlers and activation module."""

    async def fake_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    with (
        patch("mitko.bot.handlers.get_db", fake_get_db),
        patch("mitko.bot.activation.get_db", fake_get_db),
    ):
        yield
