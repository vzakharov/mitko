"""Async utility helpers."""

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class Throttler:
    """Single-process rate limiter. Not safe for multi-worker deployments."""

    min_interval: float
    _last_at: float = field(default=0.0, init=False, repr=False)

    async def wait(self) -> None:
        while (
            remaining := self.min_interval - (time.monotonic() - self._last_at)
        ) > 0:
            await asyncio.sleep(remaining)
        self._last_at = time.monotonic()
