from aiogram.types import CallbackQuery, InaccessibleMessage, Message


def get_callback_message(callback: CallbackQuery) -> Message:
    assert callback.message is not None and not isinstance(
        callback.message, InaccessibleMessage
    )
    return callback.message
