"""Conversation generation service for LLM-powered dialogue."""

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiogram import Bot
from genai_prices import calc_price
from pydantic import HttpUrl
from pydantic_ai.models.openai import (
    OpenAIChatModelSettings,
    OpenAIResponsesModelSettings,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.config import LANGUAGE_MODEL
from ..agents.conversation_agent import (
    CONVERSATION_AGENT,
    CONVERSATION_AGENT_INSTRUCTIONS,
)
from ..config import SETTINGS
from ..i18n import L
from ..models import Conversation, Generation
from ..types.messages import HistoryMessage, ProfileData
from ..utils.typing_utils import raise_error
from .conversation_utils import send_to_user
from .profiler import ProfileService

if TYPE_CHECKING:
    from pydantic_ai.run import AgentRunResult

    from ..types.messages import ConversationResponse

logger = logging.getLogger(__name__)

MESSAGE_HISTORY_MAX_LENGTH = 20


@dataclass
class ConversationGeneration:
    """Service for processing conversation generations."""

    bot: Bot
    session: AsyncSession
    generation: Generation
    conversation: Conversation

    async def execute(self) -> None:
        """Process a conversation generation: run agent, update profile, send message."""

        await self._prepare_placeholder_message()
        await self._show_thinking_status()

        try:
            user_prompt = await self._consume_user_prompt()

            result = await self._run_conversation_agent(user_prompt)

            await self._handle_agent_response(user_prompt, result)
        except Exception:
            # Notify user of failure before re-raising
            await send_to_user(
                self.bot,
                self.conversation,
                L.system.errors.GENERATION_FAILED,
                self.session,
            )
            raise

    async def _prepare_placeholder_message(self) -> None:
        """Transfer status message from conversation to generation."""
        conv = self.conversation
        if conv.status_message_id:
            self.generation.placeholder_message_id = conv.status_message_id
            conv.status_message_id = None
            await self.session.commit()

    async def _show_thinking_status(self) -> None:
        """Update placeholder to thinking emoji and send typing indicator."""
        if not self.generation.placeholder_message_id:
            return

        try:
            await self.bot.edit_message_text(
                text=L.system.THINKING,
                chat_id=self.conversation.telegram_id,
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
                chat_id=self.conversation.telegram_id, action="typing"
            )
        except Exception as e:
            logger.warning("Failed to send typing indicator: %s", e)

        logger.info(
            "Processing started, placeholder_msg_id=%s",
            self.generation.placeholder_message_id,
        )

    async def _consume_user_prompt(self) -> str:
        """Consume and clear the user_prompt from conversation."""
        user_prompt = self.conversation.user_prompt or raise_error(
            ValueError("User prompt is required")
        )
        self.conversation.user_prompt = None
        await self.session.commit()
        return user_prompt

    async def _run_conversation_agent(
        self, user_prompt: str
    ) -> "AgentRunResult[ConversationResponse]":
        """Run the conversation agent to generate a response."""

        conv = self.conversation

        instructions_with_history = "\n\n".join(
            [
                piece
                for piece in [
                    CONVERSATION_AGENT_INSTRUCTIONS,
                    self._format_history_for_instructions(conv.message_history),
                ]
                if piece
            ]
        )

        if SETTINGS.use_openai_responses_api:
            model_settings = OpenAIResponsesModelSettings(
                openai_prompt_cache_retention="24h",
            )

            if conv.last_responses_api_response_id:
                model_settings["openai_previous_response_id"] = (
                    conv.last_responses_api_response_id
                )
                try:
                    return await CONVERSATION_AGENT.run(
                        user_prompt,
                        model_settings=model_settings,
                    )
                except Exception as e:
                    if self._is_expired_response_error(e):
                        logger.warning(
                            "Responses API state expired for conversation %s (response_id=%s): %s. Falling back to history injection.",
                            conv.id,
                            conv.last_responses_api_response_id,
                            str(e),
                        )

                        conv.last_responses_api_response_id = None
                        await self.session.commit()

                        model_settings.pop("openai_previous_response_id", None)
                        return await CONVERSATION_AGENT.run(
                            user_prompt,
                            model_settings=model_settings,
                            instructions=instructions_with_history,
                        )
                    raise
            return await CONVERSATION_AGENT.run(
                user_prompt,
                model_settings=model_settings,
                instructions=instructions_with_history,
            )

        return await CONVERSATION_AGENT.run(
            user_prompt,
            model_settings=(
                OpenAIChatModelSettings(
                    openai_prompt_cache_key=str(conv.id),
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
        conv = self.conversation

        # Handle profile creation/update
        if response.profile:
            profiler = ProfileService(self.session)
            is_update = conv.user.is_complete
            await profiler.create_or_update_profile(
                conv.user, response.profile, is_update=is_update
            )

            profile_card = self._format_profile_card(response.profile)
            response_text = f"{response.utterance}\n\n{profile_card}"
        else:
            response_text = response.utterance

        await self._send_response_to_user(response_text)

        # Update conversation history for fallback
        conv.message_history = [
            *conv.message_history,
            {"role": "user", "content": user_prompt},
            {
                "role": "assistant",
                "content": json.dumps(
                    response.model_dump(), ensure_ascii=False
                ),
            },
        ]

        self._record_usage_and_cost(result)

        if response_id := result.response.provider_response_id:
            self.generation.provider_response_id = response_id
            if SETTINGS.llm_provider == "openai":
                self.generation.log_url = HttpUrl(
                    f"https://platform.openai.com/logs/{response_id}"
                )
            if SETTINGS.use_openai_responses_api:
                conv.last_responses_api_response_id = response_id

        await self.session.commit()

        logger.info(
            "Processed generation %s: message history updated",
            self.generation.id,
        )

    async def _send_response_to_user(
        self,
        response_text: str,
    ) -> None:
        """Send response to user, handling placeholder message logic."""
        conv = self.conversation
        generation = self.generation

        # Re-fetch conversation to check if new messages arrived
        await self.session.refresh(conv)
        new_messages_arrived = conv.user_prompt is not None

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
                        chat_id=conv.telegram_id,
                        message_id=generation.placeholder_message_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to edit placeholder message %d: %s, sending as new message",
                        generation.placeholder_message_id,
                        e,
                    )
                    await send_to_user(
                        self.bot, conv, response_text, self.session
                    )
            else:
                # Delete placeholder message and send response as new message (user gets notification)
                try:
                    if (
                        placeholder_message_id
                        := generation.placeholder_message_id
                    ):
                        await self.bot.delete_message(
                            chat_id=conv.telegram_id,
                            message_id=placeholder_message_id,
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to delete placeholder message %d: %s",
                        generation.placeholder_message_id,
                        e,
                    )

                await send_to_user(self.bot, conv, response_text, self.session)
        else:
            # No placeholder message (old generation) - just send response
            await send_to_user(self.bot, conv, response_text, self.session)

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
            role_label = "User" if msg["role"] == "user" else "Assistant"
            formatted_messages.append(f"{role_label}: {msg['content']}")

        return f"Previous conversation history:\n{truncation_notice}{chr(10).join(formatted_messages)}"

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
