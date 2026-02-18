"""Chat generation service for LLM-powered dialogue."""

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from genai_prices import calc_price
from pydantic import HttpUrl
from pydantic_ai.models.openai import (
    OpenAIChatModelSettings,
    OpenAIResponsesModelSettings,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.chat_agent import (
    CHAT_AGENT,
    CHAT_AGENT_INSTRUCTIONS,
)
from ..agents.config import LANGUAGE_MODEL
from ..config import SETTINGS
from ..i18n import L
from ..models import Chat, Generation
from ..types.messages import HistoryMessage, ProfileData, says
from ..utils.typing_utils import raise_error
from .chat_utils import send_to_user
from .profiler import ProfileService

if TYPE_CHECKING:
    from pydantic_ai.run import AgentRunResult

    from ..types.messages import ConversationResponse

logger = logging.getLogger(__name__)

MESSAGE_HISTORY_MAX_LENGTH = 50


@dataclass
class ChatGeneration:
    """Service for processing chat generations."""

    bot: Bot
    session: AsyncSession
    generation: Generation
    chat: Chat

    async def execute(self) -> None:
        """Process a chat generation: run agent, update profile, send message."""

        await self._prepare_placeholder_message()
        await self._show_thinking_status()

        try:
            user_prompt = await self._consume_user_prompt()

            result = await self._run_chat_agent(user_prompt)

            await self._handle_agent_response(user_prompt, result)
        except Exception:
            # Notify user of failure before re-raising
            await send_to_user(
                self.bot,
                self.chat,
                L.system.errors.GENERATION_FAILED,
                self.session,
            )
            raise

    async def _prepare_placeholder_message(self) -> None:
        """Transfer status message from chat to generation."""
        chat = self.chat
        if chat.status_message_id:
            self.generation.placeholder_message_id = chat.status_message_id
            chat.status_message_id = None
            await self.session.commit()

    async def _show_thinking_status(self) -> None:
        """Update placeholder to thinking emoji and send typing indicator."""
        if not self.generation.placeholder_message_id:
            return

        try:
            await self.bot.edit_message_text(
                text=L.system.THINKING,
                chat_id=self.chat.telegram_id,
                message_id=self.generation.placeholder_message_id,
            )
        except Exception as e:
            logger.warning(
                "Failed to edit placeholder message %d: %s",
                self.generation.placeholder_message_id,
                e,
            )

        # TODO: Consider periodic refresh every 4s to keep typing indicator alive
        try:
            await self.bot.send_chat_action(
                chat_id=self.chat.telegram_id, action="typing"
            )
        except Exception as e:
            logger.warning("Failed to send typing indicator: %s", e)

        logger.info(
            "Processing started, placeholder_msg_id=%s",
            self.generation.placeholder_message_id,
        )

    async def _consume_user_prompt(self) -> str:
        """Consume and clear the user_prompt from chat."""
        user_prompt = self.chat.user_prompt or raise_error(
            ValueError("User prompt is required")
        )
        self.chat.user_prompt = None
        await self.session.commit()
        return user_prompt

    async def _run_chat_agent(
        self, user_prompt: str
    ) -> "AgentRunResult[ConversationResponse]":
        """Run the chat agent to generate a response."""

        chat = self.chat

        instructions_with_history = "\n\n".join(
            [
                piece
                for piece in [
                    CHAT_AGENT_INSTRUCTIONS,
                    self._format_history_for_instructions(chat.message_history),
                ]
                if piece
            ]
        )

        if SETTINGS.use_openai_responses_api:
            model_settings = OpenAIResponsesModelSettings(
                openai_prompt_cache_retention="24h",
            )

            if chat.last_responses_api_response_id:
                model_settings["openai_previous_response_id"] = (
                    chat.last_responses_api_response_id
                )
                try:
                    return await CHAT_AGENT.run(
                        user_prompt,
                        model_settings=model_settings,
                    )
                except Exception as e:
                    if self._is_expired_response_error(e):
                        logger.warning(
                            "Responses API state expired for chat %s (response_id=%s): %s. Falling back to history injection.",
                            chat.id,
                            chat.last_responses_api_response_id,
                            str(e),
                        )

                        chat.last_responses_api_response_id = None
                        await self.session.commit()

                        model_settings.pop("openai_previous_response_id", None)
                        return await CHAT_AGENT.run(
                            user_prompt,
                            model_settings=model_settings,
                            instructions=instructions_with_history,
                        )
                    raise
            return await CHAT_AGENT.run(
                user_prompt,
                model_settings=model_settings,
                instructions=instructions_with_history,
            )

        return await CHAT_AGENT.run(
            user_prompt,
            model_settings=(
                OpenAIChatModelSettings(
                    openai_prompt_cache_key=str(chat.id),
                )
                if SETTINGS.llm_provider == "openai"
                else None
            ),
            instructions=instructions_with_history,
        )

    async def _handle_agent_response(
        self,
        user_prompt: str,
        result: "AgentRunResult[ConversationResponse]",
    ) -> None:
        """Handle agent response: update profile, send message, update history."""
        response = result.output
        chat = self.chat

        # Handle profile creation/update
        if response.profile:
            from ..bot.activation import activation_keyboard

            await ProfileService(self.session).create_or_update_profile(
                chat.user,
                response.profile,
                is_update=chat.user.state == "active",
            )

            profile_card = self._format_profile_card(response.profile)
            response_text = f"{response.utterance}\n\n{profile_card}\n\n{L.PROFILE_ACTIVATION_PROMPT}"
            reply_markup = activation_keyboard(chat.telegram_id)
        else:
            response_text = response.utterance
            reply_markup = None

        await self._send_response_to_user(
            response_text, reply_markup=reply_markup
        )

        # Update chat history for fallback
        chat.message_history = [
            *chat.message_history,
            says.user(user_prompt),
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
            if SETTINGS.use_openai_responses_api:
                chat.last_responses_api_response_id = response_id

        await self.session.commit()

        logger.info(
            "Processed generation %s: message history updated",
            self.generation.id,
        )

    async def _send_response_to_user(
        self,
        response_text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        """Send response to user, handling placeholder message logic."""
        chat = self.chat
        generation = self.generation

        # Re-fetch chat to check if new messages arrived
        await self.session.refresh(chat)
        new_messages_arrived = chat.user_prompt is not None

        logger.info(
            "Completion phase: new_messages=%s",
            new_messages_arrived,
        )

        # Handle placeholder message and send response
        if self.generation.placeholder_message_id:
            if new_messages_arrived:
                # Edit placeholder message with final response
                try:
                    await self.bot.edit_message_text(
                        text=response_text,
                        chat_id=chat.telegram_id,
                        message_id=generation.placeholder_message_id,
                        reply_markup=reply_markup,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to edit placeholder message %d: %s, sending as new message",
                        generation.placeholder_message_id,
                        e,
                    )
                    await send_to_user(
                        self.bot,
                        chat,
                        response_text,
                        self.session,
                        reply_markup=reply_markup,
                    )
            else:
                # Delete placeholder message and send response as new message (user gets notification)
                try:
                    if (
                        placeholder_message_id
                        := generation.placeholder_message_id
                    ):
                        await self.bot.delete_message(
                            chat_id=chat.telegram_id,
                            message_id=placeholder_message_id,
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to delete placeholder message %d: %s",
                        generation.placeholder_message_id,
                        e,
                    )

                await send_to_user(
                    self.bot,
                    chat,
                    response_text,
                    self.session,
                    reply_markup=reply_markup,
                )
        else:
            # No placeholder message (old generation) - just send response
            await send_to_user(
                self.bot,
                chat,
                response_text,
                self.session,
                reply_markup=reply_markup,
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
                "Calculated cost for generation %s: $%.6f (%d cached + %d uncached input, %d output tokens)",
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

    def _format_history_for_instructions(
        self,
        history: list[HistoryMessage],
    ) -> str | None:
        """Format history as readable text for instructions injection.

        Includes truncation for very long conversations to avoid token overflow.
        TODO: implement summarization for longer histories.
        """
        if not history:
            return None

        # Truncate to last MESSAGE_HISTORY_MAX_LENGTH messages to avoid excessive token usage
        truncated_history = history[-MESSAGE_HISTORY_MAX_LENGTH:]
        truncation_notice = ""
        if len(history) > MESSAGE_HISTORY_MAX_LENGTH:
            truncation_notice = f"[Earlier messages truncated - showing last {MESSAGE_HISTORY_MAX_LENGTH} of {len(history)} messages]\n\n"

        formatted_messages = list[str]()
        for msg in truncated_history:
            formatted_messages.append(
                f"{msg['role'].capitalize()}: {msg['content']}"
            )

        return f"Previous chat history:\n{truncation_notice}{chr(10).join(formatted_messages)}"

    def _is_expired_response_error(self, error: Exception) -> bool:
        """Check if error indicates expired/missing Responses API response.

        Be conservative: only match specific known patterns from OpenAI.
        """
        from pydantic_ai.exceptions import ModelHTTPError

        if not isinstance(error, ModelHTTPError):
            return False

        error_message = str(error).lower()

        # Known patterns from OpenAI Responses API:
        # - "Container is expired" (HTTP 400)
        # - "not found" (HTTP 404)
        return (
            "container is expired" in error_message
            or "not found" in error_message
        )

    def _format_profile_card(self, profile: ProfileData) -> str:
        """Format profile as a user-visible card (Parts 1 + 2 only)."""
        card_parts: list[str] = [L.profile.CARD_HEADER + "\n"]

        # Role display
        roles: list[str] = []
        if profile.is_seeker:
            roles.append(L.profile.ROLE_SEEKER)
        if profile.is_provider:
            roles.append(L.profile.ROLE_PROVIDER)
        card_parts.append(
            f"{L.profile.ROLE_LABEL}: {L.profile.ROLE_SEPARATOR.join(roles)}"
        )

        # Part 1: Matching Summary (technical profile)
        card_parts.append(f"\n\n{profile.matching_summary}")

        # Part 2: Practical Context (work preferences)
        # Only display if present (may be null during lazy migration)
        if profile.practical_context:
            card_parts.append(f"\n\n{profile.practical_context}")

        # Part 3 is NEVER shown to user

        return "".join(card_parts)
