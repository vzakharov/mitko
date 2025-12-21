from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from uuid import UUID


def match_consent_keyboard(match_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Yes, connect me", callback_data=f"match_accept:{match_id}"),
                InlineKeyboardButton(text="Not interested", callback_data=f"match_reject:{match_id}"),
            ]
        ]
    )


def reset_confirmation_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Yes, reset my profile",
                    callback_data=f"reset_confirm:{telegram_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Cancel",
                    callback_data=f"reset_cancel:{telegram_id}"
                ),
            ]
        ]
    )

