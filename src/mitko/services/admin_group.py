"""Admin group service for posting messages and events."""

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..bot.utils import format_user_label
from ..config import SETTINGS
from ..i18n import L
from ..utils.async_utils import Throttler
from .chat_utils import global_throttler

# 20 msg/min group Telegram limit
_GROUP_MIN_INTERVAL = 3.0
_group_throttler = Throttler(_GROUP_MIN_INTERVAL)

if TYPE_CHECKING:
    from ..models.chat import Chat

logger = logging.getLogger(__name__)


async def post_to_admin(
    bot: Bot,
    text: str,
    *,
    thread_id: int | None = None,
    reply_to_message_id: int | None = None,
    parse_mode: str | None = None,
) -> Message:
    """Send a message to the admin supergroup, optionally in a forum topic.

    Returns the sent Message on success.
    Raises on send failures.

    Args:
        bot: Telegram Bot instance
        text: Message text
        thread_id: If provided, post into this forum topic (message_thread_id)
        parse_mode: Optional Telegram parse mode ("HTML", "Markdown", etc.)
    """

    await asyncio.gather(
        *[
            throttler.wait()
            for throttler in [_group_throttler, global_throttler]
        ]
    )
    return await bot.send_message(
        chat_id=SETTINGS.admin_group_id,
        text=text,
        message_thread_id=thread_id,
        reply_to_message_id=reply_to_message_id,
        parse_mode=parse_mode,
    )


async def mirror_to_admin_thread(
    bot: Bot,
    chat: "Chat",
    text: str,
    session: AsyncSession,
) -> None:
    """Post text to the admin forum topic for this chat, creating the topic if needed.

    Creates a named forum topic on first call and persists its message_thread_id.
    Persists admin_thread_id via session.add() + session.commit() when a new topic is created.
    Silent failure: never raises.
    """
    try:
        user = chat.user
        user_ref = format_user_label(user)
        if not chat.admin_thread_id:
            chat.admin_thread_id = (
                await bot.create_forum_topic(
                    chat_id=SETTINGS.admin_group_id,
                    name=user_ref,
                )
            ).message_thread_id
            await bot.send_message(
                chat_id=SETTINGS.admin_group_id,
                text=L.admin.CHAT_INTRO.format(user_ref=user_ref),
                message_thread_id=chat.admin_thread_id,
                parse_mode=ParseMode.MARKDOWN,
            )
            session.add(chat)
            await session.commit()

        await post_to_admin(bot, text, thread_id=chat.admin_thread_id)
    except Exception as e:
        logger.exception("Failed to mirror message to admin thread: %s", e)
