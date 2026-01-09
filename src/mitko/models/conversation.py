import uuid  # noqa: I001
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field  # pyright: ignore [reportUnknownVariableType]
from sqlmodel import Column, Relationship, SQLModel

if TYPE_CHECKING:
    from .user import User


class Conversation(SQLModel, table=True):
    __tablename__: ClassVar[Any] = "conversations"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, sa_column=Column(PGUUID(as_uuid=True), primary_key=True)
    )
    telegram_id: int = Field(foreign_key="users.telegram_id")
    messages: list[dict[str, str]] = Field(default_factory=list, sa_column=Column(JSON))
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )

    user: "User" = Relationship(back_populates="conversations")
