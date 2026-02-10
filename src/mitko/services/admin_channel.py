"""Admin channel service for posting messages and events."""

import logging
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import SETTINGS

if TYPE_CHECKING:
    from ..models.conversation import Conversation

logger = logging.getLogger(__name__)


async def post_to_admin(
    bot: Bot,
    text: str,
    *,
    thread_id: int | None = None,
    parse_mode: str | None = None,
) -> Message | None:
    """Send a message to the admin channel, optionally in a thread.

    Returns the sent Message on success, or None if admin channel is not
    configured or the send fails. Errors are logged, never raised — admin
    channel failures must never break core bot functionality.

    Args:
        bot: Telegram Bot instance
        text: Message text
        thread_id: If provided, reply to this message_id to post in its thread
        parse_mode: Optional Telegram parse mode ("HTML", "Markdown", etc.)
    """
    if SETTINGS.admin_channel_id is None:
        return None

    try:
        return await bot.send_message(
            chat_id=SETTINGS.admin_channel_id,
            text=text,
            reply_to_message_id=thread_id,
            parse_mode=parse_mode,
        )
    except Exception:
        logger.exception(
            "Failed to post to admin channel %s", SETTINGS.admin_channel_id
        )
        return None


async def mirror_to_admin_thread(
    bot: Bot,
    conv: "Conversation",
    text: str,
    session: AsyncSession,
) -> None:
    """Post text to the admin thread for this conversation, creating the thread root if needed.

    Persists admin_thread_id via session.add() + session.commit() when a new thread is created.
    Silent failure: never raises.
    """
    try:
        if (
            sent := await post_to_admin(
                bot, text, thread_id=conv.admin_thread_id
            )
        ) and (not conv.admin_thread_id):
            conv.admin_thread_id = sent.message_id
            session.add(conv)
            await session.commit()
    except Exception:
        logger.exception("Failed to mirror message to admin thread")
