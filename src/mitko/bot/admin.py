"""Admin channel router — handles messages from the configured admin channel."""

import logging

from aiogram import F, Router

from ..config import SETTINGS

logger = logging.getLogger(__name__)

admin_router: Router | None = None

if channel_id := SETTINGS.admin_channel_id:
    admin_router = Router(name="admin")
    admin_router.message.filter(F.chat.id == channel_id)
    logger.info("Admin router created for channel %d", channel_id)
else:
    logger.info("Admin channel not configured, skipping admin router")
