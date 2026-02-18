"""Profile activation handler — lets users start matching after profile is created/updated."""

import logging

from aiogram import Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from ..db import get_user
from ..i18n import L
from ..jobs.matching_scheduler import start_matching_loop
from ..models import get_db
from ..services.chat_utils import send_and_record_bot_message
from ..services.profiler import ProfileService
from .handlers import get_bot
from .utils import get_callback_message

logger = logging.getLogger(__name__)

ACTIVATED_SYSTEM_MESSAGE = "The user has pressed the 'Start matching' button."


def register_activation_handlers(router: Router) -> None:
    router.callback_query.register(
        handle_activate_profile, ActivateAction.filter()
    )


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


async def handle_activate_profile(
    callback: CallbackQuery, callback_data: ActivateAction
) -> None:
    assert callback.from_user.id == callback_data.telegram_id

    async for session in get_db():
        await ProfileService(session).activate_profile(
            await get_user(session, callback_data.telegram_id)
        )
        await send_and_record_bot_message(
            get_bot(),
            callback_data.telegram_id,
            L.keyboards.activate.ACTIVATED,
            session,
            prefix=None,
            system_message=ACTIVATED_SYSTEM_MESSAGE,
            system_before_assistant=True,
        )

    start_matching_loop()
    await get_callback_message(callback).edit_reply_markup(reply_markup=None)
