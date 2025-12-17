from sqlalchemy import ForeignKey, String, Text, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from datetime import datetime
import uuid
from typing import Literal, TYPE_CHECKING

from ..models.base import Base

if TYPE_CHECKING:
    from .user import User
    from .match import Match

UserRole = Literal["seeker", "provider"]


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), nullable=False, unique=True)
    role: Mapped[UserRole] = mapped_column(String(20), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="profile")
    matches_a: Mapped[list["Match"]] = relationship(
        foreign_keys="Match.profile_a_id",
        back_populates="profile_a",
        cascade="all, delete-orphan",
    )
    matches_b: Mapped[list["Match"]] = relationship(
        foreign_keys="Match.profile_b_id",
        back_populates="profile_b",
        cascade="all, delete-orphan",
    )

