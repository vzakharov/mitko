import uuid  # noqa: I001
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import BigInteger, DateTime, ForeignKey, TypeDecorator, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.mutable import MutableList
from sqlmodel import Field  # pyright: ignore [reportUnknownVariableType]
from sqlmodel import Column, Relationship, SQLModel

from ..types.messages import (
    AssistantMessage,
    LLMMessage,
    SystemMessage,
    UserMessage,
)

if TYPE_CHECKING:
    from .generation import Generation
    from .user import User


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
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True),
    )
    telegram_id: int = Field(
        sa_column=Column(
            BigInteger(), ForeignKey("users.telegram_id"), nullable=False
        )
    )
    messages: list[LLMMessage] = Field(
        default_factory=list,
        sa_column=Column(MutableList.as_mutable(PydanticJSONB), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )

    user: "User" = Relationship(back_populates="conversations")
    generations: list["Generation"] = Relationship(
        back_populates="conversation"
    )
