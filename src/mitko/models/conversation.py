import uuid  # noqa: I001
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import BigInteger, DateTime, ForeignKey, func, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field  # pyright: ignore [reportUnknownVariableType]
from sqlmodel import Column, Relationship, SQLModel, col

from .types import SQLiteReadyJSONB

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

    async def get_latest_response_id(self, session: AsyncSession) -> str | None:
        """Get the provider_response_id from the latest completed generation."""
        from .generation import Generation

        result = await session.execute(
            select(Generation)
            .where(col(Generation.conversation_id) == self.id)
            .where(col(Generation.status) == "completed")
            .order_by(col(Generation.created_at).desc())
            .limit(1)
        )
        generation = result.scalar_one_or_none()
        return generation.provider_response_id if generation else None
