import uuid  # noqa: I001
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field  # pyright: ignore [reportUnknownVariableType]
from sqlmodel import Column, Relationship, SQLModel

if TYPE_CHECKING:
    from .generation import Generation
    from .user import User

MatchStatus = Literal[
    "pending", "a_accepted", "b_accepted", "connected", "rejected", "unmatched"
]


class Match(SQLModel, table=True):
    __tablename__: ClassVar[Any] = "matches"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True),
    )
    user_a_id: int = Field(
        sa_column=Column(
            BigInteger(), ForeignKey("users.telegram_id"), nullable=False
        )
    )
    user_b_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger(), ForeignKey("users.telegram_id"), nullable=True
        ),
    )
    similarity_score: float = Field(sa_column=Column(Float, nullable=False))
    match_rationale: str = Field(sa_column=Column(Text, nullable=False))
    matching_round: int = Field(
        default=1, sa_column=Column(Integer, nullable=False, server_default="1")
    )
    status: MatchStatus = Field(
        default="pending",
        sa_column=Column(String(20), nullable=False, server_default="pending"),
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )

    __table_args__ = (
        Index("ix_matches_status", "status"),
        Index("ix_matches_matching_round", "matching_round"),
    )

    user_a: "User" = Relationship(
        back_populates="matches_a",
        sa_relationship_kwargs={"foreign_keys": "Match.user_a_id"},
    )
    user_b: "User | None" = Relationship(
        back_populates="matches_b",
        sa_relationship_kwargs={"foreign_keys": "Match.user_b_id"},
    )
    generations: list["Generation"] = Relationship(back_populates="match")
