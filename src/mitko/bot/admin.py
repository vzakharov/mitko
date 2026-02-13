"""Admin channel router — handles messages from the configured admin channel."""

import logging

from aiogram import F, Router

from ..config import SETTINGS

logger = logging.getLogger(__name__)

admin_router = Router(name="admin")
admin_router.message.filter(F.chat.id == SETTINGS.admin_channel_id)
logger.info("Admin router created for channel %d", SETTINGS.admin_channel_id)
