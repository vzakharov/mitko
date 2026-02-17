"""Middleware that mirrors incoming user messages to the admin group."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import SETTINGS
from ..db import get_chat_or_none
from ..models import async_session_maker
from ..services.admin_group import mirror_to_admin_thread

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
            and event.chat.id != SETTINGS.admin_group_id
        ):
            await self._mirror_incoming(
                event.from_user.id, event.text, data["bot"]
            )
        return await handler(event, data)

    async def _mirror_incoming(
        self, telegram_id: int, text: str, bot: Bot
    ) -> None:
        try:
            async with async_session_maker() as session:
                await self._mirror_with_session(telegram_id, text, bot, session)
        except Exception:
            logger.exception(
                "Failed to mirror incoming message for telegram_id=%d",
                telegram_id,
            )

    async def _mirror_with_session(
        self, telegram_id: int, text: str, bot: Bot, session: AsyncSession
    ) -> None:
        if chat := await get_chat_or_none(session, telegram_id):
            await mirror_to_admin_thread(bot, chat, f"→ {text}", session)
