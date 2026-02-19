"""Announcement command handler — broadcasts messages to filtered users from the admin group."""

import json
import logging
from typing import Any, Literal

from aiogram import Bot, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..bot.utils import format_user_label
from ..db import (
    create_announcement,
    create_user_group,
    filter_users,
    get_announcement_or_none,
    update_announcement_status,
)
from ..i18n import L
from ..models import async_session_maker
from ..models.user import User
from ..services.admin_group import post_to_admin
from ..services.chat_utils import send_and_record_bot_message

logger = logging.getLogger(__name__)


def register_announcement_handlers(router: Router) -> None:
    router.message.register(handle_announcement, Command("announce"))
    router.callback_query.register(
        handle_announcement_callback, AnnouncementAction.filter()
    )


async def handle_announcement(message: Message) -> None:
    if not message.text:
        await message.reply(L.system.errors.MESSAGE_EMPTY)
        return

    # Format: /announce\n[optional JSON]\ntext\n[optional "system: ..."]
    lines = message.text.split("\n", 1)
    remainder = lines[1].strip() if len(lines) > 1 else ""

    filters = dict[str, Any]()
    text = remainder

    parts = remainder.split("\n", 1)
    if parts[0].strip().startswith("{"):
        try:
            filters = json.loads(parts[0].strip())
            text = parts[1].strip() if len(parts) > 1 else ""
        except json.JSONDecodeError as e:
            await message.reply(
                L.admin.announcement.PARSE_ERROR.format(error=e)
            )
            return

    for field in filters:
        if not hasattr(User, field):
            await message.reply(
                L.admin.announcement.UNKNOWN_FIELD.format(field=field)
            )
            return

    system_message: str | None = None
    text_lines = text.splitlines()
    if text_lines and text_lines[-1].startswith("system:"):
        system_message = text_lines[-1].removeprefix("system:").strip()
        text = "\n".join(text_lines[:-1]).strip()

    async with async_session_maker() as session:
        users = await filter_users(session, filters)
        group = await create_user_group(session, users)
        await create_announcement(
            session, group, message.message_id, text, system_message
        )

    await message.reply(
        L.admin.announcement.PREVIEW.format(
            count=len(users),
            users_preview=", ".join(
                f"[{format_user_label(user)}](tg://user?id={user.telegram_id})"
                for user in users[:10]
            ),
            text=text,
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=announcement_confirmation_keyboard(message.message_id),
    )


class AnnouncementAction(CallbackData, prefix="announcement"):
    """Callback data for announcement confirmation actions.

    The announcement payload is stored in the DB keyed by source_message_id.
    """

    action: Literal["yes", "cancel"]
    source_message_id: int


def announcement_confirmation_keyboard(
    source_message_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.admin.announcement.YES,
                    callback_data=AnnouncementAction(
                        action="yes", source_message_id=source_message_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=L.admin.announcement.CANCEL,
                    callback_data=AnnouncementAction(
                        action="cancel", source_message_id=source_message_id
                    ).pack(),
                ),
            ]
        ]
    )


async def handle_announcement_callback(
    callback: CallbackQuery, callback_data: AnnouncementAction, bot: Bot
) -> None:
    async with async_session_maker() as session:
        announcement = await get_announcement_or_none(
            session, callback_data.source_message_id
        )
        if announcement is None:
            await callback.answer()
            return

        if callback_data.action == "cancel":
            await session.delete(announcement)
            await session.commit()
            await callback.answer(L.admin.announcement.CANCELLED)
            return

        text = announcement.text
        system_message = announcement.system_message
        source_message_id = announcement.source_message_id
        users = [m.user for m in announcement.group.members]
        await update_announcement_status(session, announcement, "sending")

    sent, total = await _send_announcement(
        bot, users, text, system_message, source_message_id
    )
    await post_to_admin(
        bot,
        L.admin.announcement.DONE.format(sent=sent, total=total),
        reply_to_message_id=source_message_id,
    )


async def _send_announcement(
    bot: Bot,
    users: list[User],
    text: str,
    system_message: str | None,
    source_message_id: int,
) -> tuple[int, int]:
    sent = 0
    for user in users:
        try:
            async with async_session_maker() as session:
                await send_and_record_bot_message(
                    bot,
                    user.telegram_id,
                    text,
                    session,
                    system_message=system_message,
                )
            sent += 1
        except Exception:
            logger.exception(
                "Failed to send announcement to telegram_id=%d",
                user.telegram_id,
            )

    async with async_session_maker() as session:
        announcement = await get_announcement_or_none(
            session, source_message_id
        )
        if announcement is not None:
            await update_announcement_status(
                session,
                announcement,
                # TODO: handle partial failures with an additional m2m table
                "sent" if sent > 0 else "failed",
            )

    return sent, len(users)
