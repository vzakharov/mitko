from aiogram import Bot, Dispatcher

from ..config import settings
from .handlers import router, set_bot_instance


def create_bot() -> Bot:
    """Create and configure Bot instance"""
    return Bot(token=settings.telegram_bot_token)


def create_dispatcher() -> Dispatcher:
    """Create and configure Dispatcher with all routers"""
    dp = Dispatcher()
    dp.include_router(router)
    return dp


def initialize_bot() -> tuple[Bot, Dispatcher]:
    """Initialize bot, dispatcher, and set global instance"""
    bot = create_bot()
    set_bot_instance(bot)
    dp = create_dispatcher()
    return bot, dp
