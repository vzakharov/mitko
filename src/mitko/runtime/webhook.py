from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Request, Response

from ..config import SETTINGS
from ..jobs.generation_processor import (
    start_generation_processor,
    stop_generation_processor,
)
from ..jobs.matching_scheduler import (
    start_matching_loop,
    stop_matching_loop,
)


class WebhookRuntime:
    """Webhook-based runtime for production deployment"""

    async def startup(self, bot: Bot, dp: Dispatcher) -> None:
        """Set webhook with Telegram"""
        if SETTINGS.telegram_webhook_url is None:
            raise ValueError(
                "TELEGRAM_WEBHOOK_URL is required for webhook mode"
            )

        await bot.set_webhook(
            url=SETTINGS.telegram_webhook_url,
            secret_token=SETTINGS.telegram_webhook_secret,
        )

    async def shutdown(self, bot: Bot, dp: Dispatcher) -> None:
        """Delete webhook and close session"""
        await bot.delete_webhook()
        await bot.session.close()

    async def run(self, bot: Bot, dp: Dispatcher) -> None:
        """No-op: FastAPI handles requests via uvicorn"""
        pass

    def create_app(self, bot: Bot, dp: Dispatcher) -> FastAPI:
        """Create FastAPI app with webhook endpoint and lifespan"""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            await self.startup(bot, dp)
            start_matching_loop()
            start_generation_processor(bot)
            yield
            await stop_generation_processor()
            stop_matching_loop()
            await self.shutdown(bot, dp)

        app = FastAPI(lifespan=lifespan)

        @app.post("/webhook/{secret_path:str}")
        async def webhook_handler(
            request: Request, secret_path: str
        ) -> Response:
            if (
                SETTINGS.telegram_webhook_secret
                and secret_path != SETTINGS.telegram_webhook_secret
            ):
                return Response(status_code=403)

            update_dict = await request.json()
            update = Update(**update_dict)
            await dp.feed_update(bot, update)
            return Response(status_code=200)

        @app.get("/health")
        async def health_check():
            return {"status": "ok"}

        # Reference decorated functions to satisfy pyright (they're used by FastAPI)
        _ = (webhook_handler, health_check)

        return app
