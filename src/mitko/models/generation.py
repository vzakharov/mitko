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
    from .match import Match

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
    conversation_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="conversations.id",
    )
    match_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="matches.id",
    )
    scheduled_for: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    status: GenerationStatus = Field(
        default="pending",
        sa_column=Column(String(20), nullable=False),
    )
    # TODO: Move placeholder_message_id to Conversation model
    # Currently used only for conversation generations to show "Thinking 🤔" status.
    # Should be moved to Conversation.status_message_id pattern for cleaner separation.
    placeholder_message_id: int | None = Field(
        default=None,
        description="Telegram message ID used as placeholder during generation processing",
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when generation status changed to 'started'",
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
    cost_usd: float | None = Field(
        default=None,
        description="Total cost in USD for this generation",
    )

    conversation: "Conversation | None" = Relationship(
        back_populates="generations"
    )
    match: "Match | None" = Relationship(back_populates="generations")
