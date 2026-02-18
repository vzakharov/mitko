import logging

from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent

from ..i18n import L
from ..settings_instance import SETTINGS
from .admin import admin_router
from .bot_instance import create_bot
from .errors import BotError
from .handlers import router
from .mirroring_middleware import MessageMirrorMiddleware

logger = logging.getLogger(__name__)


def create_dispatcher() -> Dispatcher:
    """Create and configure Dispatcher with all routers"""
    dp = Dispatcher()
    dp.include_router(
        admin_router
    )  # Admin first — higher priority than user router
    dp.include_router(router)
    router.message.middleware(MessageMirrorMiddleware())
    logger.info("Admin router registered for group %d", SETTINGS.admin_group_id)

    async def handle_error(event: ErrorEvent) -> bool:
        # Log with full traceback. We must do this ourselves because returning True
        # suppresses aiogram's built-in error logging.
        logger.exception("Unhandled error in handler", exc_info=event.exception)

        text = (
            event.exception.user_message
            if isinstance(event.exception, BotError)
            else L.system.errors.SOMETHING_WENT_WRONG
        )

        update = event.update
        if update.message:
            await update.message.answer(text)
        elif update.callback_query:
            await update.callback_query.answer(text, show_alert=True)

        return True

    dp.errors()(handle_error)
    return dp


def initialize_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    """Initialize bot, dispatcher, and set global instance"""
    return create_bot(), create_dispatcher()
