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

