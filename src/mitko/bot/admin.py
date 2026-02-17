"""Admin group router — handles messages from the configured admin group."""

from aiogram import F, Router

from ..config import SETTINGS
from .announce import register_announce_handlers

admin_router = Router(name="admin")
for observer in [
    admin_router.message,
    admin_router.channel_post,
    admin_router.callback_query,
]:
    observer.filter(F.chat.id == SETTINGS.admin_group_id)

register_announce_handlers(admin_router)
