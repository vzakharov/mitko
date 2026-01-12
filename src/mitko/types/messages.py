"""Message types for LLM conversations.

This module contains the core message types used throughout the application
to represent different roles in a conversation (user, system, assistant).
These types are shared by both models (for storage) and agents (for processing).
"""

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel
from sqlmodel import Field  # pyright: ignore [reportUnknownVariableType]

if TYPE_CHECKING:
    from ..agents.models import ConversationResponse


class UserMessage(BaseModel):
    """A user message in the conversation."""

    role: Literal["user"]
    content: str

    @staticmethod
    def create(content: str) -> "UserMessage":
        return UserMessage(role="user", content=content)


class SystemMessage(BaseModel):
    """A system message in the conversation."""

    role: Literal["system"]
    content: str

    @staticmethod
    def create(content: str) -> "SystemMessage":
        return SystemMessage(role="system", content=content)


class AssistantMessage(BaseModel):
    """An assistant message with structured response."""

    role: Literal["assistant"]
    content: "ConversationResponse"

    @staticmethod
    def create(content: "ConversationResponse") -> "AssistantMessage":
        return AssistantMessage(role="assistant", content=content)


# Discriminated union using role field
LLMMessage = Annotated[
    UserMessage | SystemMessage | AssistantMessage, Field(discriminator="role")
]
