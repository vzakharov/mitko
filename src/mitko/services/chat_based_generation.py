"""Base class for chat-based generation services with Responses API support."""

import json
import logging
from abc import ABC
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import (
    OpenAIChatModelSettings,
    OpenAIResponsesModelSettings,
)

from ..agents.chat_agent import CHAT_AGENT
from ..config import SETTINGS
from ..models import Chat
from ..types.messages import says
from ..utils.collection_utils import compact
from .base_generation import MESSAGE_HISTORY_MAX_LENGTH, BaseGenerationService

if TYPE_CHECKING:
    from pydantic_ai.run import AgentRunResult

    from ..types.messages import ConversationResponse

logger = logging.getLogger(__name__)


@dataclass
class ChatBasedGeneration(BaseGenerationService["ConversationResponse"], ABC):
    """Base class for chat-based generation services.

    Provides shared infrastructure for:
    - Message history building
    - Responses API with fallback to message history injection
    - Expired response error detection
    - Chat history updates

    Subclasses must implement execute() with their specific logic.
    """

    chat: Chat

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

    async def _run_chat_agent(
        self, user_prompt: str | None
    ) -> "AgentRunResult[ConversationResponse]":
        """Run the chat agent with Responses API support and fallback.

        This method handles:
        1. Responses API with continuation via previous_response_id
        2. Fallback to message history injection if response expired
        3. Standard prompt caching when Responses API is disabled

        Args:
            user_prompt: The user's input prompt (can be None for system-driven generation)

        Returns:
            Agent run result with ConversationResponse
        """
        chat = self.chat

        if SETTINGS.use_openai_responses_api:
            model_settings = OpenAIResponsesModelSettings(
                openai_prompt_cache_retention="24h",
            )

            async def run_fallback():
                return await CHAT_AGENT.run(
                    user_prompt,
                    model_settings=model_settings,
                    message_history=self._build_message_history(),
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
                        return await run_fallback()
                    raise
            return await run_fallback()

        return await CHAT_AGENT.run(
            user_prompt,
            model_settings=(
                OpenAIChatModelSettings(
                    openai_prompt_cache_key=str(chat.id),
                )
                if SETTINGS.llm_provider == "openai"
                else None
            ),
            message_history=self._build_message_history(),
        )

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

    def _update_chat_history(
        self, user_prompt: str | None, response: "ConversationResponse"
    ) -> None:
        """Update chat history with user prompt and assistant response.

        Args:
            user_prompt: The user's input (can be None for system-driven generation)
            response: The agent's response
        """
        self.chat.message_history = compact(
            *self.chat.message_history,
            says.user(user_prompt) if user_prompt else None,
            says.assistant(
                json.dumps(response.model_dump(), ensure_ascii=False)
            ),
        )
