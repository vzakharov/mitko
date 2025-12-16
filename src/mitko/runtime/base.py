from typing import Protocol

from aiogram import Bot, Dispatcher


class BotRuntime(Protocol):
    """Abstract interface for bot runtime modes (webhook, polling, etc.)"""

    async def startup(self, bot: Bot, dp: Dispatcher) -> None:
        """Runtime-specific startup (e.g., set webhook)"""
        ...

    async def run(self, bot: Bot, dp: Dispatcher) -> None:
        """Run the bot (blocking in polling mode, no-op in webhook mode)"""
        ...

    async def shutdown(self, bot: Bot, dp: Dispatcher) -> None:
        """Runtime-specific cleanup (e.g., delete webhook, close session)"""
        ...
