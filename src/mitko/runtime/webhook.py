from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiohttp import web
from fastapi import FastAPI, Request

from ..config import settings
from ..jobs.matching import start_matching_scheduler, stop_matching_scheduler


class WebhookRuntime:
    """Webhook-based runtime for production deployment"""

    async def startup(self, bot: Bot, dp: Dispatcher) -> None:
        """Set webhook with Telegram"""
        await bot.set_webhook(
            url=settings.telegram_webhook_url,
            secret_token=settings.telegram_webhook_secret,
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
            start_matching_scheduler(bot)
            yield
            stop_matching_scheduler()
            await self.shutdown(bot, dp)

        app = FastAPI(lifespan=lifespan)

        @app.post("/webhook/{secret_path:str}")
        async def webhook_handler(request: Request, secret_path: str) -> web.Response:
            if settings.telegram_webhook_secret and secret_path != settings.telegram_webhook_secret:
                return web.Response(status=403)

            update_dict = await request.json()
            update = Update(**update_dict)
            await dp.feed_update(bot, update)
            return web.Response(status=200)

        @app.get("/health")
        async def health_check():
            return {"status": "ok"}

        return app
