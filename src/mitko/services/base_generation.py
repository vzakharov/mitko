"""Base class for LLM generation services."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiogram import Bot
from genai_prices import calc_price
from pydantic import HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.config import LANGUAGE_MODEL
from ..config import SETTINGS
from ..models import Generation

if TYPE_CHECKING:
    from pydantic_ai.run import AgentRunResult

logger = logging.getLogger(__name__)

# Shared constant for message history truncation
MESSAGE_HISTORY_MAX_LENGTH = 50

# Generic type parameter for agent output type


@dataclass
class BaseGenerationService[T](ABC):
    """Base class for LLM generation services.

    Provides shared infrastructure for:
    - Token usage and cost tracking
    - Provider response ID bookkeeping

    Subclasses must implement execute() with their specific logic.
    """

    bot: Bot
    session: AsyncSession
    generation: Generation

    @abstractmethod
    async def execute(self) -> None:
        """Execute the generation task. Must be implemented by subclasses."""

    def record_usage_and_cost(
        self,
        result: "AgentRunResult[T]",
        log_context: str,
    ) -> None:
        """Record token usage and calculate cost.

        Args:
            result: Agent run result containing usage information
            log_context: Context string for logging (e.g., "generation", "match intro generation")
        """
        usage = result.usage()
        gen = self.generation
        gen.cached_input_tokens = usage.cache_read_tokens
        gen.uncached_input_tokens = usage.input_tokens - usage.cache_read_tokens
        gen.output_tokens = usage.output_tokens

        try:
            price_data = calc_price(
                usage,
                model_ref=LANGUAGE_MODEL.model_name,
                provider_id=SETTINGS.llm_provider,
            )
            gen.cost_usd = float(price_data.total_price)

            logger.info(
                "Calculated cost for %s %s: $%.6f (%d cached + %d uncached input, %d output tokens)",
                log_context,
                gen.id,
                gen.cost_usd,
                gen.cached_input_tokens or 0,
                gen.uncached_input_tokens or 0,
                gen.output_tokens or 0,
            )
        except Exception as e:
            logger.warning(
                "Failed to calculate cost for %s %s: %s",
                log_context,
                gen.id,
                str(e),
                exc_info=True,
            )
            gen.cost_usd = None

    def record_provider_response(self, result: "AgentRunResult[T]") -> None:
        """Record provider response ID and log URL if available."""
        if response_id := result.response.provider_response_id:
            self.generation.provider_response_id = response_id
            if SETTINGS.llm_provider == "openai":
                self.generation.log_url = HttpUrl(
                    f"https://platform.openai.com/logs/{response_id}"
                )
