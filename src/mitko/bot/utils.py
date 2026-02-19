from aiogram.types import CallbackQuery, InaccessibleMessage, Message

from ..models.user import User


def get_callback_message(callback: CallbackQuery) -> Message:
    assert callback.message is not None and not isinstance(
        callback.message, InaccessibleMessage
    )
    return callback.message


def format_user_label(user: User) -> str:
    return f"@{user.username}" if user.username else f"#{user.telegram_id}"
