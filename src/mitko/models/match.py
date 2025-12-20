from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import DateTime, func, Text, Float, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from datetime import datetime
import uuid
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .user import User

MatchStatus = Literal["pending", "a_accepted", "b_accepted", "connected", "rejected"]


class Match(SQLModel, table=True):
    __tablename__ = "matches"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True)
    )
    user_a_id: int = Field(foreign_key="users.telegram_id")
    user_b_id: int = Field(foreign_key="users.telegram_id")
    similarity_score: float = Field(sa_column=Column(Float))
    match_rationale: str = Field(sa_column=Column(Text))
    status: MatchStatus = Field(default="pending", sa_column=Column(String(20)))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )

    user_a: "User" = Relationship(
        back_populates="matches_a",
        sa_relationship_kwargs={"foreign_keys": "Match.user_a_id"}
    )
    user_b: "User" = Relationship(
        back_populates="matches_b",
        sa_relationship_kwargs={"foreign_keys": "Match.user_b_id"}
    )

