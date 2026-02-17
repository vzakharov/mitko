"""Announce command handler — broadcasts messages to filtered users from the admin group."""

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

from ..db import (
    create_announce,
    create_user_group,
    filter_users,
    get_announce_or_none,
    update_announce_status,
)
from ..i18n import L
from ..models import async_session_maker
from ..models.user import User
from ..services.admin_group import post_to_admin
from ..services.chat_utils import send_to_user

logger = logging.getLogger(__name__)


def register_announce_handlers(router: Router) -> None:
    router.message.register(handle_announce, Command("announce"))
    router.channel_post.register(handle_announce, Command("announce"))
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

    assert message.message_thread_id is not None

    async with async_session_maker() as session:
        users = await filter_users(session, filters)
        group = await create_user_group(session, users)
        await create_announce(session, group, message.message_thread_id, text)

    await message.reply(
        L.admin.announce.PREVIEW.format(
            count=len(users),
            users_preview=", ".join(
                f"tg://user?id={user.telegram_id}" for user in users[:10]
            ),
            text=text,
        ),
        reply_markup=announce_confirmation_keyboard(message.message_thread_id),
    )


class AnnounceAction(CallbackData, prefix="announce"):
    """Callback data for announce confirmation actions.

    The announce payload is stored in the DB keyed by thread_id.
    """

    action: Literal["yes", "cancel"]
    thread_id: int


def announce_confirmation_keyboard(
    thread_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.admin.announce.YES,
                    callback_data=AnnounceAction(
                        action="yes", thread_id=thread_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=L.admin.announce.CANCEL,
                    callback_data=AnnounceAction(
                        action="cancel", thread_id=thread_id
                    ).pack(),
                ),
            ]
        ]
    )


async def handle_announce_callback(
    callback: CallbackQuery, callback_data: AnnounceAction, bot: Bot
) -> None:
    if callback.message is None or isinstance(
        callback.message, InaccessibleMessage
    ):
        await callback.answer()
        return

    async with async_session_maker() as session:
        announce = await get_announce_or_none(session, callback_data.thread_id)
        if announce is None:
            await callback.answer()
            return

        if callback_data.action == "cancel":
            await session.delete(announce)
            await session.commit()
            await callback.answer(L.admin.announce.CANCELLED)
            return

        text = announce.text
        thread_id = announce.thread_id
        users = [m.user for m in announce.group.members]
        await update_announce_status(session, announce, "sending")

    sent, total = await _send_announce(bot, users, text, thread_id)
    await post_to_admin(
        bot,
        L.admin.announce.DONE.format(sent=sent, total=total),
        thread_id=thread_id,
    )


async def _send_announce(
    bot: Bot, users: list[User], text: str, thread_id: int
) -> tuple[int, int]:
    sent = 0
    for user in users:
        try:
            async with async_session_maker() as session:
                await send_to_user(bot, user.telegram_id, text, session)
            sent += 1
        except Exception:
            logger.exception(
                "Failed to send announce to telegram_id=%d", user.telegram_id
            )

    async with async_session_maker() as session:
        announce = await get_announce_or_none(session, thread_id)
        if announce is not None:
            await update_announce_status(
                session,
                announce,
                # TODO: handle partial failures with an additional m2m table
                "sent" if sent > 0 else "failed",
            )

    return sent, len(users)
