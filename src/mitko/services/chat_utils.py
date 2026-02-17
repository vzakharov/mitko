"""Utilities for chat message handling."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_chat, get_chat_or_none
from ..models.chat import Chat
from ..types.messages import says
from ..utils.async_utils import Throttler
from ..utils.typing_utils import raise_error

# 1 msg/s per DM chat (Telegram limit)
_DM_MIN_INTERVAL = 1.0

logger = logging.getLogger(__name__)

INJECTED_MESSAGE_PREFIX = "[Admin-injected message - not LLM-generated - stored for memory continuity]"

_GLOBAL_MIN_INTERVAL = 1 / 30  # 30 msg/s global Telegram limit
global_throttler = Throttler(_GLOBAL_MIN_INTERVAL)


async def _get_telegram_id_and_chat(
    recipient: Chat | int,
    session: AsyncSession,
) -> tuple[int, Chat]:
    return (
        (recipient.telegram_id, recipient)
        if isinstance(recipient, Chat)
        else (recipient, await get_chat(session, recipient))
    )


async def send_to_user(
    bot: Bot,
    recipient: Chat | int,
    text: str,
    session: AsyncSession,
    **kwargs: Any,
) -> Message:
    """Send a message to the user and mirror it to their admin group thread.

    Args:
        bot: Telegram Bot instance
        recipient: Chat object or raw telegram_id (int)
        text: Message text
        session: DB session (used to persist admin_thread_id if a new thread is created)
        **kwargs: Forwarded to bot.send_message (e.g. reply_markup, parse_mode)
    """
    telegram_id, chat = await _get_telegram_id_and_chat(recipient, session)

    if (
        remaining := _DM_MIN_INTERVAL
        - (datetime.now(UTC) - chat.updated_at).total_seconds()
    ) > 0:
        await asyncio.sleep(remaining)

    await global_throttler.wait()
    result = await bot.send_message(telegram_id, text, **kwargs)

    await _mirror_outgoing(bot, telegram_id, text, session, chat)

    return result


async def _mirror_outgoing(
    bot: Bot,
    telegram_id: int,
    text: str,
    session: AsyncSession,
    chat: Chat | None,
) -> None:
    """Mirror an outgoing message to the admin group thread for this user."""
    from .admin_group import mirror_to_admin_thread

    try:
        chat = (
            chat
            or await get_chat_or_none(session, telegram_id)
            or raise_error(
                ValueError(f"No chat found for telegram_id={telegram_id}")
            )
        )

        await mirror_to_admin_thread(bot, chat, f"← {text}", session)
    except Exception as e:
        logger.exception(
            "Failed to mirror outgoing message for telegram_id=%d: %s",
            telegram_id,
            e,
        )


async def send_and_record_bot_message(
    bot: Bot,
    chat: Chat | int,
    message_text: str,
    session: AsyncSession,
    prefix: str = INJECTED_MESSAGE_PREFIX,
) -> None:
    """
    Send a bot-initiated message to the user and record it in chat history.

    This is used for bot-initiated messages (not LLM-generated responses):
    - Profile update prompts when profiler version changes
    - Announcements or notifications
    - Any message where the bot needs to "remember" what it said

    The message is stored with a prefix to distinguish it from LLM responses.
    Invalidates OpenAI Responses API state to force history injection on next turn.

    Args:
        chat: Either a Chat object with telegram_id and message_history or a raw telegram_id (int)
        message_text: The text to send (plain text, formatted with markdown)
        bot: Telegram Bot instance
        session: DB session for committing history
    """
    _, chat = await _get_telegram_id_and_chat(chat, session)
    chat.message_history = [
        *chat.message_history,
        says.assistant(f"{prefix} {message_text}"),
    ]

    chat.last_responses_api_response_id = None

    session.add(chat)
    await send_to_user(bot, chat, message_text, session)
    await session.commit()
