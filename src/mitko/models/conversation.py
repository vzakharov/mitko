import uuid  # noqa: I001
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal

from pydantic import BaseModel
from sqlalchemy import DateTime, TypeDecorator, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.mutable import MutableList
from sqlmodel import Field  # pyright: ignore [reportUnknownVariableType]
from sqlmodel import Column, Relationship, SQLModel

if TYPE_CHECKING:
    from .user import User

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
    content: ConversationResponse

    @staticmethod
    def create(content: ConversationResponse) -> "AssistantMessage":
        return AssistantMessage(role="assistant", content=content)


# Discriminated union using role field
LLMMessage = Annotated[UserMessage | SystemMessage | AssistantMessage, Field(discriminator="role")]


class PydanticJSONB(TypeDecorator[list[LLMMessage]]):
    """Custom SQLAlchemy type for serializing/deserializing Pydantic message models."""

    impl = JSON
    cache_ok = True

    def process_bind_param(
        self, value: list[LLMMessage] | None, dialect: Any
    ) -> list[dict[str, Any]] | None:
        """Serialize Pydantic models to JSON-compatible dicts for storage."""
        if value is None:
            return None
        return [msg.model_dump(mode="json") for msg in value]

    def process_result_value(
        self, value: list[dict[str, Any]] | None, dialect: Any
    ) -> list[LLMMessage] | None:
        """Deserialize JSON dicts back to Pydantic models."""
        if value is None:
            return None

        result: list[LLMMessage] = []
        for item in value:
            role = item.get("role")
            if role == "user":
                result.append(UserMessage.model_validate(item))
            elif role == "assistant":
                result.append(AssistantMessage.model_validate(item))
            elif role == "system":
                result.append(SystemMessage.model_validate(item))
            else:
                raise ValueError(f"Unknown role: {role}")

        return result


class Conversation(SQLModel, table=True):
    __tablename__: ClassVar[Any] = "conversations"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, sa_column=Column(PGUUID(as_uuid=True), primary_key=True)
    )
    telegram_id: int = Field(foreign_key="users.telegram_id")
    messages: list[LLMMessage] = Field(
        default_factory=list, sa_column=Column(MutableList.as_mutable(PydanticJSONB))
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )
    scheduled_for: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    user: "User" = Relationship(back_populates="conversations")
