"""Announce command handler — broadcasts messages to filtered users from the admin channel."""

import json
import logging
import re
from typing import Any, Literal

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    CallbackQuery,
    InaccessibleMessage,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import filter_users
from ..i18n import L
from ..models import async_session_maker
from ..models.user import User
from ..services.admin_channel import post_to_admin
from ..services.chat_utils import global_throttler, send_to_user

logger = logging.getLogger(__name__)

# Pending announce payloads: source_message_id → (filters, text)
_pending_announces: dict[int, tuple[dict[str, Any], str]] = {}


def register_announce_handlers(router: Router) -> None:
    router.message.register(handle_announce, Command("announce"))
    router.callback_query.register(
        handle_announce_callback, AnnounceAction.filter()
    )


async def handle_announce(message: Message) -> None:
    if not message.text:
        await message.reply(L.system.errors.MESSAGE_EMPTY)
        return

    remainder = re.sub(r"^/announce\S*\s*", "", message.text).strip()

    filters = dict[str, Any]()
    text = remainder

    if remainder.startswith("{"):
        try:
            decoder = json.JSONDecoder()
            filters, end_idx = decoder.raw_decode(remainder)
            text = remainder[end_idx:].strip()
        except json.JSONDecodeError as e:
            await message.reply(L.admin.announce.PARSE_ERROR.format(error=e))
            return

    for field in filters:
        if not hasattr(User, field):
            await message.reply(
                L.admin.announce.UNKNOWN_FIELD.format(field=field)
            )
            return

    async with async_session_maker() as session:
        users = await filter_users(session, filters)

    assert message.message_id is not None
    _pending_announces[message.message_id] = (filters, text)

    await message.reply(
        L.admin.announce.PREVIEW.format(
            count=len(users),
            users_preview=", ".join(
                f"tg://user?id={user.telegram_id}" for user in users[:10]
            ),
            text=text,
        ),
        reply_markup=announce_confirmation_keyboard(message.message_id),
    )


class AnnounceAction(CallbackData, prefix="announce"):
    """Callback data for announce confirmation actions.

    The announce payload (filters + text) is stored in _pending_announces
    keyed by source_message_id to avoid callback_data size limits.
    """

    action: Literal["yes", "cancel"]
    source_message_id: int


def announce_confirmation_keyboard(
    source_message_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.admin.announce.YES,
                    callback_data=AnnounceAction(
                        action="yes", source_message_id=source_message_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=L.admin.announce.CANCEL,
                    callback_data=AnnounceAction(
                        action="cancel", source_message_id=source_message_id
                    ).pack(),
                ),
            ]
        ]
    )


async def handle_announce_callback(
    callback: CallbackQuery, callback_data: AnnounceAction, bot: Bot
) -> None:
    pending = _pending_announces.pop(callback_data.source_message_id, None)
    if pending is None:
        await callback.answer()
        return

    if callback.message is None or isinstance(
        callback.message, InaccessibleMessage
    ):
        await callback.answer()
        return

    filters, text = pending

    if callback_data.action == "cancel":
        await callback.answer(L.admin.announce.CANCELLED)
        return

    async with async_session_maker() as session:
        sent, total = await _send_announce(bot, session, filters, text)

    await post_to_admin(
        bot,
        L.admin.announce.DONE.format(sent=sent, total=total),
        thread_id=callback_data.source_message_id,
    )


async def _send_announce(
    bot: Bot, session: AsyncSession, filters: dict[str, Any], text: str
) -> tuple[int, int]:
    users = await filter_users(session, filters)
    sent = 0
    for user in users:
        try:
            await global_throttler.wait()
            await send_to_user(bot, user.telegram_id, text, session)
            sent += 1
        except Exception:
            logger.exception(
                "Failed to send announce to telegram_id=%d", user.telegram_id
            )
    return sent, len(users)
