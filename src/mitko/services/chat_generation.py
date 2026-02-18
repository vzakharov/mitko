"""Chat generation service for LLM-powered dialogue."""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardMarkup

from ..i18n import L
from ..types.messages import ProfileData
from ..utils.typing_utils import raise_error
from .chat_based_generation import ChatBasedGeneration
from .chat_utils import send_to_user
from .profiler import ProfileService

if TYPE_CHECKING:
    from pydantic_ai.run import AgentRunResult

    from ..types.messages import ConversationResponse

logger = logging.getLogger(__name__)


@dataclass
class ChatGeneration(ChatBasedGeneration):
    """Service for processing chat generations."""

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

        # Update chat history and Responses API state
        self._update_chat_history(user_prompt, response)

        self.record_usage_and_cost(result, "generation")
        self.record_provider_response(result)

        # Update Responses API state for future generations
        if result.response.provider_response_id:
            chat.last_responses_api_response_id = (
                result.response.provider_response_id
            )

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
