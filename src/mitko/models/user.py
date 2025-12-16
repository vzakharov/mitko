from sqlalchemy import BigInteger, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Literal, TYPE_CHECKING

from ..models.base import Base

if TYPE_CHECKING:
    from .conversation import Conversation
    from .profile import Profile


UserRole = Literal["seeker", "provider"]
UserState = Literal["onboarding", "profiling", "active", "paused"]


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role: Mapped[UserRole | None] = mapped_column(String(20), nullable=True)
    state: Mapped[UserState] = mapped_column(String(20), default="onboarding")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    profile: Mapped["Profile | None"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)

