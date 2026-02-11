"""Async utility helpers."""

import asyncio
import time
from collections.abc import Callable


async def wait_for_interval(get_last: Callable[[], float], min_interval: float) -> float:
    """Sleep until min_interval seconds have elapsed since get_last().

    get_last is called on every loop iteration so callers can pass a lambda
    that reads a module-level variable, ensuring concurrent coroutines see
    each other's updates.
    Returns time.monotonic() at the moment the interval has elapsed.
    """
    while (remaining := min_interval - (time.monotonic() - get_last())) > 0:
        await asyncio.sleep(remaining)
    return time.monotonic()
