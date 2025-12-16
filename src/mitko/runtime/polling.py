import logging

from aiogram import Bot, Dispatcher

logger = logging.getLogger(__name__)


class PollingRuntime:
    """Long polling runtime for development"""

    async def startup(self, bot: Bot, dp: Dispatcher) -> None:
        """Optional startup logic for polling mode"""
        logger.info("Starting polling mode")

    async def run(self, bot: Bot, dp: Dispatcher) -> None:
        """Start long polling (blocking)"""
        await dp.start_polling(bot, handle_signals=True)

    async def shutdown(self, bot: Bot, dp: Dispatcher) -> None:
        """Close bot session"""
        await bot.session.close()
