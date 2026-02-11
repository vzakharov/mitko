"""Single-process Telegram send rate limiter. Not safe for multi-worker deployments."""

from ..utils.async_utils import wait_for_interval

# 30 msg/s global Telegram limit
_GLOBAL_MIN_INTERVAL = 1 / 30
_last_send_at: float = 0.0


async def wait_for_global_limit() -> None:
    global _last_send_at
    _last_send_at = await wait_for_interval(lambda: _last_send_at, _GLOBAL_MIN_INTERVAL)
