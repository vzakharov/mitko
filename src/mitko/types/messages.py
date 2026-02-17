"""Message types for LLM conversations.

This module contains the core message types used throughout the application
to represent different roles in a conversation (user, system, assistant).
These types are shared by both models (for storage) and agents (for processing).
"""

from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, field_validator, model_validator
from sqlmodel import Field


class HistoryMessage(TypedDict):
    """A message in the conversation history (user or assistant)."""

    role: Literal["user", "assistant", "system"]
    content: str


class _Says:
    def user(self, content: str) -> HistoryMessage:
        return HistoryMessage(role="user", content=content)

    def assistant(self, content: str) -> HistoryMessage:
        return HistoryMessage(role="assistant", content=content)

    def system(self, content: str) -> HistoryMessage:
        return HistoryMessage(role="system", content=content)


says = _Says()


class ProfileData(BaseModel):
    """Structured profile data extracted from conversation"""

    is_seeker: bool
    is_provider: bool
    matching_summary: str
    practical_context: str
    private_observations: str | None = None

    @model_validator(mode="after")
    def validate_roles(self) -> "ProfileData":
        """Ensure at least one role is enabled"""
        if not (self.is_seeker or self.is_provider):
            raise ValueError(
                "Profile must have at least one role enabled (is_seeker or is_provider)"
            )
        return self

    @field_validator("matching_summary", "practical_context")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Ensure required fields are not empty"""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    @field_validator("private_observations")
    @classmethod
    def validate_optional_field(cls, v: str | None) -> str | None:
        """Ensure optional field is either None or non-empty"""
        if v is not None and not v.strip():
            return None
        return v.strip() if v else None


class ConversationResponse(BaseModel):
    """Unified response from conversational agent"""

    utterance: str
    profile: ProfileData | None = None

    @field_validator("utterance")
    @classmethod
    def validate_utterance(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Utterance cannot be empty")
        return v.strip()


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
    content: ConversationResponse

    @staticmethod
    def create(content: ConversationResponse) -> "AssistantMessage":
        return AssistantMessage(role="assistant", content=content)


# Discriminated union using role field
LLMMessage = Annotated[
    UserMessage | SystemMessage | AssistantMessage, Field(discriminator="role")
]
