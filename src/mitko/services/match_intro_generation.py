"""Match intro generation service for personalized match notifications."""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..bot.keyboards import match_consent_keyboard
from ..i18n import L
from .chat_based_generation import ChatBasedGeneration
from .chat_utils import send_to_user

if TYPE_CHECKING:
    from pydantic_ai.run import AgentRunResult

    from ..types.messages import ConversationResponse

logger = logging.getLogger(__name__)

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
class MatchIntroGeneration(ChatBasedGeneration):
    """Service for processing match intro generations."""

    async def execute(self) -> None:
        """Generate personalized match intro and send to user.

        IMPORTANT: The system message was already injected and committed
        by MatchGeneration before this generation was created.
        Future user messages will see BOTH the system message AND
        the assistant response in their conversation history.
        """

        try:
            result = await self._run_chat_agent(None)
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

    async def _send_intro_to_user(
        self,
        result: "AgentRunResult[ConversationResponse]",
    ) -> None:
        """Send personalized intro with match consent keyboard."""
        response = result.output
        assert self.generation.match is not None

        # Send intro message with match consent keyboard
        await send_to_user(
            self.bot,
            self.chat,
            response.utterance,
            self.session,
            reply_markup=match_consent_keyboard(self.generation.match.id),
        )

        # Update chat history (no user prompt - system message drives generation)
        self._update_chat_history(None, response)

        # Update Responses API state for future generations
        if self.generation.match.status == "qualified":
            self.chat.last_responses_api_response_id = (
                result.response.provider_response_id
            )

        self.record_usage_and_cost(result, "match intro generation")
        self.record_provider_response(result)

        await self.session.commit()

        logger.info(
            "Processed match intro generation %s for match %s: message history updated",
            self.generation.id,
            self.generation.match.id,
        )
