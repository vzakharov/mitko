from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import JSON, UUID as PGUUID
from datetime import datetime
from typing import TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from .user import User

class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True)
    )
    telegram_id: int = Field(foreign_key="users.telegram_id")
    messages: list[dict[str, str]] = Field(
        default_factory=list,
        sa_column=Column(JSON)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now()
        )
    )

    user: "User" = Relationship(back_populates="conversations")

