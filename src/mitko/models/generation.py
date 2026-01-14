import uuid  # noqa: I001
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import HttpUrl
from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field  # pyright: ignore [reportUnknownVariableType]
from sqlmodel import Column, Relationship, SQLModel

from .types import HttpUrlType

if TYPE_CHECKING:
    from .conversation import Conversation

GenerationStatus = Literal["pending", "started", "completed", "failed"]


class Generation(SQLModel, table=True):
    __tablename__: ClassVar[Any] = "generations"
    __table_args__: ClassVar[Any] = (
        Index("ix_generations_status", "status"),
        Index("ix_generations_scheduled_for", "scheduled_for"),
        Index("ix_generations_conversation_id", "conversation_id"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True),
    )
    conversation_id: uuid.UUID = Field(
        foreign_key="conversations.id",
    )
    scheduled_for: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    status: GenerationStatus = Field(
        default="pending",
        sa_column=Column(String(20), nullable=False),
    )
    placeholder_message_id: int | None = Field(
        default=None,
        description="Telegram message ID used as placeholder during generation processing",
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )

    cached_input_tokens: int | None = Field(
        default=None,
        description="Number of tokens read from cache during generation",
    )
    uncached_input_tokens: int | None = Field(
        default=None,
        description="Number of non-cached input tokens (input_tokens - cache_read_tokens)",
    )
    output_tokens: int | None = Field(
        default=None,
        description="Number of output/completion tokens generated",
    )
    provider_response_id: str | None = Field(
        default=None,
        description="Provider's unique response identifier for tracking",
    )
    log_url: HttpUrl | None = Field(
        default=None,
        sa_type=HttpUrlType,
        description="URL to view logs in provider platform (OpenAI only)",
    )

    conversation: "Conversation" = Relationship(back_populates="generations")
