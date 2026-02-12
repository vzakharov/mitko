"""Admin channel service for posting messages and events."""

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import SETTINGS
from ..i18n import L
from ..utils.async_utils import Throttler
from ..utils.typing_utils import raise_error
from .chat_utils import global_throttler

# 20 msg/min channel Telegram limit
_CHANNEL_MIN_INTERVAL = 3.0
_channel_throttler = Throttler(_CHANNEL_MIN_INTERVAL)

if TYPE_CHECKING:
    from ..models.chat import Chat

logger = logging.getLogger(__name__)


async def _post_to_admin(
    bot: Bot,
    text: str,
    *,
    thread_id: int | None = None,
    parse_mode: str | None = None,
) -> Message:
    """Send a message to the admin channel, optionally in a thread.

    Returns the sent Message on success.
    Raises on send failures or if admin channel is not configured.

    Args:
        bot: Telegram Bot instance
        text: Message text
        thread_id: If provided, reply to this message_id to post in its thread
        parse_mode: Optional Telegram parse mode ("HTML", "Markdown", etc.)
    """

    await asyncio.gather(
        *[
            throttler.wait()
            for throttler in [_channel_throttler, global_throttler]
        ]
    )
    return await bot.send_message(
        chat_id=SETTINGS.admin_channel_id
        or raise_error(RuntimeError("Admin channel is not configured")),
        text=text,
        reply_to_message_id=thread_id,
        parse_mode=parse_mode,
    )


async def mirror_to_admin_thread(
    bot: Bot,
    chat: "Chat",
    text: str,
    session: AsyncSession,
) -> None:
    """Post text to the admin thread for this chat, creating the thread root if needed.

    Sends a separate header message (from i18n) as the thread root on first call.
    Persists admin_thread_id via session.add() + session.commit() when a new thread is created.
    Silent failure: never raises.
    """
    try:
        if not chat.admin_thread_id:
            chat.admin_thread_id = (
                await _post_to_admin(
                    bot,
                    L.admin.CHAT_HEADER.format(user_id=chat.telegram_id),
                    parse_mode="Markdown",
                )
            ).message_id
            session.add(chat)
            await session.commit()

        await _post_to_admin(bot, text, thread_id=chat.admin_thread_id)
    except Exception as e:
        logger.exception("Failed to mirror message to admin thread: %s", e)
