import asyncio
import logging

from fastapi import FastAPI

from .bot.core import initialize_bot
from .config import SETTINGS
from .jobs.generation_processor import (
    start_generation_processor,
    stop_generation_processor,
)
from .jobs.matching_scheduler import (
    start_matching_loop,
    stop_matching_loop,
)
from .runtime.polling import PollingRuntime
from .runtime.webhook import WebhookRuntime

logger = logging.getLogger(__name__)


def get_runtime():
    """Factory function to select runtime based on config"""
    if SETTINGS.telegram_mode == "webhook":
        if not SETTINGS.telegram_webhook_url:
            raise ValueError("Webhook mode requires TELEGRAM_WEBHOOK_URL")
        logger.info("Using webhook mode")
        return WebhookRuntime()
    else:
        logger.info("Using polling mode")
        return PollingRuntime()


# For webhook mode (uvicorn entry point)
# Only initialize when imported by uvicorn, not when run directly
app: FastAPI | None = None
if SETTINGS.telegram_mode == "webhook" and __name__ != "__main__":
    bot, dp = initialize_bot()
    runtime = WebhookRuntime()
    app = runtime.create_app(bot, dp)


# For polling mode (direct execution)
async def main():
    """Main entry point for polling mode"""
    bot, dp = initialize_bot()
    runtime = get_runtime()

    try:
        await runtime.startup(bot, dp)
        start_matching_loop()
        start_generation_processor(bot)
        await runtime.run(bot, dp)
    finally:
        await stop_generation_processor()
        stop_matching_loop()
        await runtime.shutdown(bot, dp)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
