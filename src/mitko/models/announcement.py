import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from sqlalchemy import VARCHAR, BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .user_group import UserGroup

AnnouncementStatus = Literal["pending", "sending", "sent", "failed"]


class Announcement(SQLModel, table=True):
    __tablename__: ClassVar[Any] = "announcements"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True),
    )
    group_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("user_groups.id"),
            nullable=False,
            unique=True,
        )
    )
    source_message_id: int = Field(
        sa_column=Column(BigInteger(), nullable=False, unique=True)
    )
    text: str = Field(sa_column=Column(Text(), nullable=False))
    status: AnnouncementStatus = Field(
        default="pending",
        sa_column=Column(VARCHAR(20), nullable=False, server_default="pending"),
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )

    group: "UserGroup" = Relationship()
