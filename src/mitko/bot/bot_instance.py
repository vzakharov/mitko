from aiogram import Bot

from ..settings_instance import SETTINGS

_bot_instance: Bot | None = None


def create_bot() -> Bot:
    """Create and configure Bot instance"""
    global _bot_instance
    _bot_instance = Bot(token=SETTINGS.telegram_bot_token)
    return _bot_instance


def get_bot() -> Bot:
    """Get the global Bot instance.
    Raises RuntimeError if the instance is not set.
    """
    if _bot_instance is None:
        raise RuntimeError("Bot instance not set")
    return _bot_instance
