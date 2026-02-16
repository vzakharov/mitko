import logging

from aiogram import Bot, Dispatcher

from ..config import SETTINGS
from .admin import admin_router
from .handlers import router, set_bot_instance
from .mirroring_middleware import MessageMirrorMiddleware

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    """Create and configure Bot instance"""
    return Bot(token=SETTINGS.telegram_bot_token)


def create_dispatcher() -> Dispatcher:
    """Create and configure Dispatcher with all routers"""
    dp = Dispatcher()
    dp.include_router(admin_router)  # Admin first — higher priority than user router
    dp.include_router(router)
    router.message.middleware(MessageMirrorMiddleware())
    logger.info("Admin router registered for channel %d", SETTINGS.admin_channel_id)
    return dp


def initialize_bot() -> tuple[Bot, Dispatcher]:
    """Initialize bot, dispatcher, and set global instance"""
    bot = create_bot()
    set_bot_instance(bot)
    dp = create_dispatcher()
    return bot, dp
