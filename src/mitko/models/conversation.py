import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import (
    Column,
    Field,  # pyright: ignore [reportUnknownVariableType]
    Relationship,
    SQLModel,
)

from ..types.messages import HistoryMessage
from .types import JSONBList, SQLiteReadyJSONB

if TYPE_CHECKING:
    from .generation import Generation
    from .user import User


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
    message_history_json: bytes = Field(
        default=b"[]",
        sa_column=Column(SQLiteReadyJSONB(), nullable=False),
        description="Serialized PydanticAI message history (JSON bytes)",
    )
    user_prompt: str | None = Field(
        default=None,
        description="Pending user input to be processed in next generation",
    )
    last_responses_api_response_id: str | None = Field(
        default=None,
        description="OpenAI Responses API response ID for conversation continuation. Only used when USE_OPENAI_RESPONSES_API=true. Cleared on conversation reset.",
    )
    history: list[HistoryMessage] = Field(
        default_factory=list,
        sa_column=Column(JSONBList(), nullable=False, server_default="[]"),
        description="Conversation history for fallback when Responses API state expires.",
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
    status_message_id: int | None = Field(
        default=None,
        description="Telegram message ID for status updates (edit/delete)",
    )

    user: "User" = Relationship(back_populates="conversations")
    generations: list["Generation"] = Relationship(
        back_populates="conversation"
    )
