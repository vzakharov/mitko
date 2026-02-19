"""Reusable factories for fake aiogram types used in handler tests."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import NamedTuple
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Message
from aiogram.types import Chat as TgChat
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession


class FakeMessage(NamedTuple):
    message: Message
    answer: AsyncMock


class FakeCallback(NamedTuple):
    callback: CallbackQuery
    answer: AsyncMock
    msg_edit_text: AsyncMock
    msg_answer: AsyncMock


def make_message(
    text: str = "hello",
    user_id: int = 12345,
    message_id: int = 1,
) -> FakeMessage:
    """Create a fake Message with mocked answer/reply methods."""
    answer_mock = AsyncMock(name="message.answer")
    msg = Message(
        message_id=message_id,
        date=datetime.now(),
        chat=TgChat(id=user_id, type="private"),
        from_user=TgUser(id=user_id, is_bot=False, first_name="Test"),
        text=text,
    )
    object.__setattr__(msg, "answer", answer_mock)
    return FakeMessage(message=msg, answer=answer_mock)


def make_callback(
    data: str,
    user_id: int = 12345,
    message_id: int = 1,
) -> FakeCallback:
    """Create a fake CallbackQuery with mocked answer method and attached message."""
    edit_text_mock = AsyncMock(name="message.edit_text")
    msg_answer_mock = AsyncMock(name="message.answer")
    cb_answer_mock = AsyncMock(name="callback.answer")

    inner_msg = Message(
        message_id=message_id,
        date=datetime.now(),
        chat=TgChat(id=user_id, type="private"),
        from_user=TgUser(id=user_id, is_bot=False, first_name="Test"),
        text="original",
    )
    object.__setattr__(inner_msg, "edit_text", edit_text_mock)
    object.__setattr__(inner_msg, "answer", msg_answer_mock)
    object.__setattr__(
        inner_msg,
        "edit_reply_markup",
        AsyncMock(name="message.edit_reply_markup"),
    )

    cb = CallbackQuery(
        id="test_cb_1",
        chat_instance="test",
        from_user=TgUser(id=user_id, is_bot=False, first_name="Test"),
        message=inner_msg,
        data=data,
    )
    object.__setattr__(cb, "answer", cb_answer_mock)
    return FakeCallback(
        callback=cb,
        answer=cb_answer_mock,
        msg_edit_text=edit_text_mock,
        msg_answer=msg_answer_mock,
    )


@asynccontextmanager
async def patch_get_db(
    session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Context manager that patches get_db in both handlers and activation module."""
    from unittest.mock import patch

    async def fake_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    with (
        patch("mitko.bot.handlers.get_db", fake_get_db),
        patch("mitko.bot.activation.get_db", fake_get_db),
    ):
        yield
