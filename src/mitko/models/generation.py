import uuid  # noqa: I001
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field  # pyright: ignore [reportUnknownVariableType]
from sqlmodel import Column, Relationship, SQLModel

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

    conversation: "Conversation" = Relationship(back_populates="generations")
