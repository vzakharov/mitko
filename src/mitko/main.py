from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher
from aiohttp import web
import logging

from .config import settings
from .bot.handlers import router, set_bot_instance
from .jobs.matching import start_matching_scheduler

logger = logging.getLogger(__name__)

bot = Bot(token=settings.telegram_bot_token)
set_bot_instance(bot)
dp = Dispatcher()
dp.include_router(router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.telegram_webhook_url:
        await bot.set_webhook(
            url=settings.telegram_webhook_url,
            secret_token=settings.telegram_webhook_secret,
        )
    start_matching_scheduler(bot)
    yield
    if settings.telegram_webhook_url:
        await bot.delete_webhook()


app = FastAPI(lifespan=lifespan)


@app.post("/webhook/{secret_path:str}")
async def webhook_handler(request: Request, secret_path: str) -> web.Response:
    if settings.telegram_webhook_secret and secret_path != settings.telegram_webhook_secret:
        return web.Response(status=403)

    update_dict = await request.json()
    from aiogram.types import Update
    update = Update(**update_dict)
    await dp.feed_update(bot, update)
    return web.Response(status=200)


@app.get("/health")
async def health_check():
    return {"status": "ok"}

