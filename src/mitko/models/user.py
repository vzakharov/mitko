from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import BigInteger, DateTime, Text, func
from pgvector.sqlalchemy import Vector
from datetime import datetime
from typing import Literal, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .conversation import Conversation
    from .match import Match


UserState = Literal["onboarding", "profiling", "active", "paused"]


class User(SQLModel, table=True):
    __tablename__ = "users"

    telegram_id: int = Field(sa_type=BigInteger(), primary_key=True)

    # Role flags
    is_seeker: bool | None = Field(default=None)
    is_provider: bool | None = Field(default=None)

    # State management
    state: UserState = Field(default="onboarding", max_length=20)

    # Profile data (formerly in Profile model)
    summary: str | None = Field(default=None, sa_column=Column(Text))
    embedding: Any = Field(default=None, sa_type=Vector(1536))
    is_complete: bool = Field(default=False)

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )

    conversations: list["Conversation"] = Relationship(back_populates="user")
    matches_a: list["Match"] = Relationship(
        back_populates="user_a",
        sa_relationship_kwargs={
            "foreign_keys": "Match.user_a_id",
            "cascade": "all, delete-orphan",
        }
    )
    matches_b: list["Match"] = Relationship(
        back_populates="user_b",
        sa_relationship_kwargs={
            "foreign_keys": "Match.user_b_id",
            "cascade": "all, delete-orphan",
        }
    )

    @property
    def has_role(self) -> bool:
        """Check if user has at least one role assigned"""
        return bool(self.is_seeker or self.is_provider)

    @property
    def roles_display(self) -> str:
        """Human-readable role description"""
        if self.is_seeker and self.is_provider:
            return "both seeker and provider"
        elif self.is_seeker:
            return "seeker"
        elif self.is_provider:
            return "provider"
        else:
            return "unknown"

    def can_match_with(self, other: "User") -> bool:
        """Check if this user can be matched with another (seeker ↔ provider only)"""
        return (self.is_seeker and other.is_provider) or (self.is_provider and other.is_seeker)

