import asyncio
import logging

from fastapi import FastAPI

from .bot.core import initialize_bot
from .config import settings
from .jobs.matching import start_matching_scheduler, stop_matching_scheduler
from .runtime.polling import PollingRuntime
from .runtime.webhook import WebhookRuntime

logger = logging.getLogger(__name__)


def get_runtime():
    """Factory function to select runtime based on config"""
    if settings.telegram_mode == "webhook":
        if not settings.telegram_webhook_url:
            raise ValueError("Webhook mode requires TELEGRAM_WEBHOOK_URL")
        logger.info("Using webhook mode")
        return WebhookRuntime()
    else:
        logger.info("Using polling mode")
        return PollingRuntime()


# For webhook mode (uvicorn entry point)
# Only initialize when imported by uvicorn, not when run directly
app: FastAPI | None = None
if settings.telegram_mode == "webhook" and __name__ != "__main__":
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
        start_matching_scheduler(bot)
        await runtime.run(bot, dp)
    finally:
        stop_matching_scheduler()
        await runtime.shutdown(bot, dp)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

