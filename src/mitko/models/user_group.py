import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .user import User


class UserGroup(SQLModel, table=True):
    __tablename__: ClassVar[Any] = "user_groups"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True),
    )
    name: str | None = Field(
        default=None,
        sa_column=Column(Text(), nullable=True, unique=True),
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )

    members: list["UserGroupMember"] = Relationship(
        back_populates="group",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class UserGroupMember(SQLModel, table=True):
    __tablename__: ClassVar[Any] = "user_group_members"

    group_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("user_groups.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    user_id: int = Field(
        sa_column=Column(
            BigInteger(),
            ForeignKey("users.telegram_id"),
            primary_key=True,
        )
    )

    group: "UserGroup" = Relationship(back_populates="members")
    user: "User" = Relationship()
