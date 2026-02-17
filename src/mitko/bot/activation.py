"""Profile activation handler — lets users start matching after profile is created/updated."""

import logging

from aiogram import Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    CallbackQuery,
    InaccessibleMessage,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from ..db import get_or_create_user
from ..i18n import L
from ..models import get_db
from ..services.profiler import ProfileService

logger = logging.getLogger(__name__)


class ActivateAction(CallbackData, prefix="activate"):
    telegram_id: int


def activation_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L.keyboards.activate.ACTIVATE,
                    callback_data=ActivateAction(
                        telegram_id=telegram_id
                    ).pack(),
                )
            ]
        ]
    )


def register_activation_handlers(router: Router) -> None:
    router.callback_query.register(
        handle_activate_profile, ActivateAction.filter()
    )


async def handle_activate_profile(
    callback: CallbackQuery, callback_data: ActivateAction
) -> None:
    if callback.from_user.id != callback_data.telegram_id:
        await callback.answer(L.system.errors.UNAUTHORIZED, show_alert=True)
        return

    if callback.message is None or isinstance(
        callback.message, InaccessibleMessage
    ):
        await callback.answer(
            L.system.errors.MESSAGE_UNAVAILABLE, show_alert=True
        )
        return

    async for session in get_db():
        user = await get_or_create_user(session, callback_data.telegram_id)

        if user.state not in ("ready", "updated"):
            await callback.answer(
                L.matching.errors.ALREADY_PROCESSED, show_alert=True
            )
            return

        await ProfileService(session).activate_profile(user)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(L.keyboards.activate.ACTIVATED)
