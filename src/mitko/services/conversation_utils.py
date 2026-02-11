"""Utilities for conversation message handling."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_conversation, get_conversation_or_none
from ..models.conversation import Conversation
from ..utils.async_utils import Throttler
from ..utils.typing_utils import raise_error
from .admin_channel import mirror_to_admin_thread

# 1 msg/s per DM chat (Telegram limit)
_DM_MIN_INTERVAL = 1.0

logger = logging.getLogger(__name__)

INJECTED_MESSAGE_PREFIX = "[Admin-injected message - not LLM-generated - stored for memory continuity]"

_GLOBAL_MIN_INTERVAL = 1 / 30  # 30 msg/s global Telegram limit
global_throttler = Throttler(_GLOBAL_MIN_INTERVAL)


async def send_to_user(
    bot: Bot,
    recipient: Conversation | int,
    text: str,
    session: AsyncSession,
    **kwargs: Any,
) -> Message:
    """Send a message to the user and mirror it to their admin channel thread.

    Args:
        bot: Telegram Bot instance
        recipient: Conversation object or raw telegram_id (int)
        text: Message text
        session: DB session (used to persist admin_thread_id if a new thread is created)
        **kwargs: Forwarded to bot.send_message (e.g. reply_markup, parse_mode)
    """
    telegram_id, conv = (
        (recipient.telegram_id, recipient)
        if isinstance(recipient, Conversation)
        else (recipient, await get_conversation(session, recipient))
    )

    if (
        remaining := _DM_MIN_INTERVAL
        - (datetime.now(UTC) - conv.updated_at).total_seconds()
    ) > 0:
        await asyncio.sleep(remaining)

    await global_throttler.wait()
    result = await bot.send_message(telegram_id, text, **kwargs)

    await _mirror_outgoing(bot, telegram_id, text, session, conv)

    return result


async def _mirror_outgoing(
    bot: Bot,
    telegram_id: int,
    text: str,
    session: AsyncSession,
    conv: Conversation | None,
) -> None:
    """Mirror an outgoing message to the admin channel thread for this user."""
    try:
        conv = (
            conv
            or await get_conversation_or_none(session, telegram_id)
            or raise_error(
                ValueError(
                    f"No conversation found for telegram_id={telegram_id}"
                )
            )
        )

        await mirror_to_admin_thread(bot, conv, f"← {text}", session)
    except Exception as e:
        logger.exception(
            "Failed to mirror outgoing message for telegram_id=%d: %s",
            telegram_id,
            e,
        )


async def send_and_record_bot_message(
    conversation: Conversation,
    message_text: str,
    bot: Bot,
    session: AsyncSession,
    prefix: str = INJECTED_MESSAGE_PREFIX,
) -> None:
    """
    Send a bot-initiated message to the user and record it in conversation history.

    This is used for bot-initiated messages (not LLM-generated responses):
    - Profile update prompts when profiler version changes
    - Announcements or notifications
    - Any message where the bot needs to "remember" what it said

    The message is stored with a prefix to distinguish it from LLM responses.
    Invalidates OpenAI Responses API state to force history injection on next turn.

    Args:
        conversation: Conversation object with telegram_id and message_history
        message_text: The text to send (plain text, formatted with markdown)
        bot: Telegram Bot instance
        session: DB session for committing history
    """
    conversation.message_history = [
        *conversation.message_history,
        {"role": "assistant", "content": f"{prefix} {message_text}"},
    ]

    conversation.last_responses_api_response_id = None

    session.add(conversation)
    await send_to_user(bot, conversation, message_text, session)
    await session.commit()
