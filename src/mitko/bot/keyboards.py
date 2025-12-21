from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData
from uuid import UUID
from typing import Literal


class MatchAction(CallbackData, prefix="match"):
    """Callback data for match consent actions"""
    action: Literal["accept", "reject"]
    match_id: str  # UUID as string for serialization


class ResetAction(CallbackData, prefix="reset"):
    """Callback data for profile reset actions"""
    action: Literal["confirm", "cancel"]
    telegram_id: int


def match_consent_keyboard(match_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Yes, connect me",
                    callback_data=MatchAction(action="accept", match_id=str(match_id)).pack()
                ),
                InlineKeyboardButton(
                    text="Not interested",
                    callback_data=MatchAction(action="reject", match_id=str(match_id)).pack()
                ),
            ]
        ]
    )


def reset_confirmation_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Yes, reset my profile",
                    callback_data=ResetAction(action="confirm", telegram_id=telegram_id).pack()
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Cancel",
                    callback_data=ResetAction(action="cancel", telegram_id=telegram_id).pack()
                ),
            ]
        ]
    )

