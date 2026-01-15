from datetime import datetime  # noqa: I001
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import VARCHAR, BigInteger, DateTime, Index, Text, func
from sqlmodel import Field  # pyright: ignore [reportUnknownVariableType]
from sqlmodel import Column, Relationship, SQLModel

if TYPE_CHECKING:
    from .conversation import Conversation
    from .match import Match


UserState = Literal["onboarding", "profiling", "active", "paused"]


class User(SQLModel, table=True):
    __tablename__: ClassVar[Any] = "users"

    telegram_id: int = Field(sa_column=Column(BigInteger(), primary_key=True))

    # Role flags
    is_seeker: bool | None = Field(default=None)
    is_provider: bool | None = Field(default=None)

    # State management
    state: UserState = Field(
        default="onboarding",
        sa_column=Column(
            VARCHAR(20), nullable=False, server_default="onboarding"
        ),
    )

    # Profile data (formerly in Profile model)
    summary: str | None = Field(default=None, sa_column=Column(Text))

    embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(1536), nullable=True)
    )
    is_complete: bool = Field(default=False)

    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )

    __table_args__ = (
        Index(
            "ix_users_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    conversations: list["Conversation"] = Relationship(back_populates="user")
    matches_a: list["Match"] = Relationship(
        back_populates="user_a",
        sa_relationship_kwargs={
            "foreign_keys": "Match.user_a_id",
            "cascade": "all, delete-orphan",
        },
    )
    matches_b: list["Match"] = Relationship(
        back_populates="user_b",
        sa_relationship_kwargs={
            "foreign_keys": "Match.user_b_id",
            "cascade": "all, delete-orphan",
        },
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
        return bool(
            (self.is_seeker and other.is_provider)
            or (self.is_provider and other.is_seeker)
        )
