from sqlalchemy import ForeignKey, String, Text, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from typing import TYPE_CHECKING, Literal

from ..models.base import Base

if TYPE_CHECKING:
    from .user import User

MatchStatus = Literal["pending", "a_accepted", "b_accepted", "connected", "rejected"]


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_a_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), nullable=False)
    user_b_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    match_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[MatchStatus] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user_a: Mapped["User"] = relationship(foreign_keys=[user_a_id], back_populates="matches_a")
    user_b: Mapped["User"] = relationship(foreign_keys=[user_b_id], back_populates="matches_b")

