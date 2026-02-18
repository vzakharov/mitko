"""Match intro generation service for personalized match notifications."""

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiogram import Bot
from genai_prices import calc_price
from pydantic import HttpUrl
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModelSettings
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.chat_agent import CHAT_AGENT
from ..agents.config import LANGUAGE_MODEL
from ..bot.keyboards import match_consent_keyboard
from ..config import SETTINGS
from ..i18n import L
from ..models import Chat, Generation
from ..types.messages import says
from .chat_utils import send_to_user

if TYPE_CHECKING:
    from pydantic_ai.run import AgentRunResult

    from ..types.messages import ConversationResponse

logger = logging.getLogger(__name__)

MESSAGE_HISTORY_MAX_LENGTH = 50

MATCH_INTRO_SYSTEM_MESSAGE_TEMPLATE = """
You have found a potential match for this user!

MATCHED USER'S PROFILE:
{profile_display}

WHY THIS MATCH MIGHT WORK:
{rationale}

YOUR TASK:
Generate a warm, personalized introduction to this match that:
- Mentions the match's **first** (not last!) name, if known from the profile
- References relevant context from your conversation history with the user
- Smoothly transitions into introducing the matched profile
- Adapts tone based on past interactions
- Highlights why this particular match aligns with what they've shared
- Keeps it conversational and engaging

DO NOT:
- Expose the internal reasoning verbatim
- Mention the qualification process
- Use formulaic templates

The match consent buttons will be automatically attached to your message.
""".strip()


@dataclass
class MatchIntroGeneration:
    """Service for processing match intro generations."""

    bot: Bot
    session: AsyncSession
    generation: Generation
    chat: Chat

    async def execute(self) -> None:
        """Generate personalized match intro and send to user.

        IMPORTANT: The system message was already injected and committed
        by MatchGeneration before this generation was created.
        Future user messages will see BOTH the system message AND
        the assistant response in their conversation history.
        """

        try:
            result = await self._run_chat_agent()
            await self._send_intro_to_user(result)
        except Exception:
            # Notify user of failure before re-raising
            await send_to_user(
                self.bot,
                self.chat,
                L.system.errors.GENERATION_FAILED,
                self.session,
            )
            raise

    async def _run_chat_agent(self) -> "AgentRunResult[ConversationResponse]":
        """Run the chat agent to generate a personalized intro.

        The system message in chat history contains match context and instructions.
        No user_prompt is needed - the system message drives generation.
        """
        # Use empty user prompt - system message drives the generation
        user_prompt = ""

        return await CHAT_AGENT.run(
            user_prompt,
            model_settings=(
                OpenAIChatModelSettings(
                    openai_prompt_cache_key=str(self.chat.id),
                )
                if SETTINGS.llm_provider == "openai"
                else None
            ),
            message_history=self._build_message_history(),
        )

    async def _send_intro_to_user(
        self,
        result: "AgentRunResult[ConversationResponse]",
    ) -> None:
        """Send personalized intro with match consent keyboard."""
        response = result.output
        chat = self.chat
        assert self.generation.match is not None

        # Send intro message with match consent keyboard
        await send_to_user(
            self.bot,
            chat,
            response.utterance,
            self.session,
            reply_markup=match_consent_keyboard(self.generation.match.id),
        )

        # Record in chat history as assistant message
        # Note: The system message was already added by MatchGeneration
        chat.message_history = [
            *chat.message_history,
            says.assistant(
                json.dumps(response.model_dump(), ensure_ascii=False)
            ),
        ]

        self._record_usage_and_cost(result)

        if response_id := result.response.provider_response_id:
            self.generation.provider_response_id = response_id
            if SETTINGS.llm_provider == "openai":
                self.generation.log_url = HttpUrl(
                    f"https://platform.openai.com/logs/{response_id}"
                )

        await self.session.commit()

        logger.info(
            "Processed match intro generation %s for match %s: message history updated",
            self.generation.id,
            self.generation.match.id,
        )

    def _record_usage_and_cost(
        self,
        result: "AgentRunResult[ConversationResponse]",
    ) -> None:
        """Record token usage and calculate cost."""
        usage = result.usage()
        gen = self.generation
        gen.cached_input_tokens = usage.cache_read_tokens
        gen.uncached_input_tokens = usage.input_tokens - usage.cache_read_tokens
        gen.output_tokens = usage.output_tokens

        # Calculate cost using genai-prices
        try:
            price_data = calc_price(
                usage,
                model_ref=LANGUAGE_MODEL.model_name,
                provider_id=SETTINGS.llm_provider,
            )
            gen.cost_usd = float(price_data.total_price)

            logger.info(
                "Calculated cost for match intro generation %s: $%.6f (%d cached + %d uncached input, %d output tokens)",
                gen.id,
                gen.cost_usd,
                gen.cached_input_tokens or 0,
                gen.uncached_input_tokens or 0,
                gen.output_tokens or 0,
            )
        except Exception as e:
            # Fail gracefully - cost calculation should not break generation processing
            logger.warning(
                "Failed to calculate cost for generation %s: %s",
                gen.id,
                str(e),
                exc_info=True,
            )
            gen.cost_usd = None

    def _build_message_history(self) -> list[ModelRequest | ModelResponse]:
        """Convert stored HistoryMessage list to PydanticAI ModelMessage objects."""
        return [
            ModelResponse(parts=[TextPart(content=msg["content"])])
            if msg["role"] == "assistant"
            else ModelRequest(
                parts=[
                    (
                        UserPromptPart
                        if msg["role"] == "user"
                        else SystemPromptPart
                    )(content=msg["content"])
                ]
            )
            for msg in self.chat.message_history[-MESSAGE_HISTORY_MAX_LENGTH:]
        ]
