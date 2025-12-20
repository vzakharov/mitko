from sqlalchemy import BigInteger, String, DateTime, Boolean, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from datetime import datetime
from typing import Literal, TYPE_CHECKING

from ..models.base import Base

if TYPE_CHECKING:
    from .conversation import Conversation
    from .match import Match


UserState = Literal["onboarding", "profiling", "active", "paused"]


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # Role flags
    is_seeker: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_provider: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # State management
    state: Mapped[UserState] = mapped_column(String(20), default="onboarding")

    # Profile data (formerly in Profile model)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    matches_a: Mapped[list["Match"]] = relationship(
        foreign_keys="Match.user_a_id",
        back_populates="user_a",
        cascade="all, delete-orphan",
    )
    matches_b: Mapped[list["Match"]] = relationship(
        foreign_keys="Match.user_b_id",
        back_populates="user_b",
        cascade="all, delete-orphan",
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

