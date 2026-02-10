"""Middleware that mirrors incoming user messages to the admin channel."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, TelegramObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..config import SETTINGS
from ..models import async_session_maker
from ..models.conversation import Conversation
from ..services.admin_channel import mirror_to_admin_thread

logger = logging.getLogger(__name__)


class MessageMirrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if (
            isinstance(event, Message)
            and event.text
            and event.from_user
            and (
                SETTINGS.admin_channel_id is None
                or event.chat.id != SETTINGS.admin_channel_id
            )
        ):
            await self._mirror_incoming(event.from_user.id, event.text, data["bot"])
        return await handler(event, data)

    async def _mirror_incoming(self, telegram_id: int, text: str, bot: Bot) -> None:
        try:
            async with async_session_maker() as session:
                await self._mirror_with_session(telegram_id, text, bot, session)
        except Exception:
            logger.exception(
                "Failed to mirror incoming message for telegram_id=%d", telegram_id
            )

    async def _mirror_with_session(
        self, telegram_id: int, text: str, bot: Bot, session: AsyncSession
    ) -> None:
        result = await session.execute(
            select(Conversation).where(col(Conversation.telegram_id) == telegram_id)
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            return
        await mirror_to_admin_thread(bot, conv, f"→ {text}", session)
