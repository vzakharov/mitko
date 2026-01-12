"""Message types for LLM conversations.

This module contains the core message types used throughout the application
to represent different roles in a conversation (user, system, assistant).
These types are shared by both models (for storage) and agents (for processing).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, field_validator, model_validator
from sqlmodel import Field  # pyright: ignore [reportUnknownVariableType]


class ProfileData(BaseModel):
    """Structured profile data extracted from conversation"""

    is_seeker: bool
    is_provider: bool
    summary: str

    @model_validator(mode="after")
    def validate_roles(self) -> "ProfileData":
        """Ensure at least one role is enabled"""
        if not (self.is_seeker or self.is_provider):
            raise ValueError(
                "Profile must have at least one role enabled (is_seeker or is_provider)"
            )
        return self

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, v: str) -> str:
        """Ensure summary is not empty"""
        if not v or not v.strip():
            raise ValueError("Summary cannot be empty")
        return v.strip()


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
