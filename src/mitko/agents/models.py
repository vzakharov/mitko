"""Pydantic models for structured LLM outputs"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MatchQualification(BaseModel):
    """Match evaluation result with decision and internal reasoning"""

    explanation: str = Field(
        description=(
            "Internal reasoning explaining why this match is qualified or disqualified. "
            "Focus on objective evaluation - this is agent-to-agent communication, "
            "not user-facing messaging."
        )
    )
    decision: Literal["qualified", "disqualified"] = Field(
        description=(
            "Match quality decision: 'qualified' means match is worthwhile and should be "
            "presented to users; 'disqualified' means match isn't strong enough."
        )
    )

    @field_validator("explanation")
    @classmethod
    def validate_explanation(cls, v: str) -> str:
        """Ensure explanation is not empty"""
        if not v or not v.strip():
            raise ValueError("Explanation cannot be empty")
        return v.strip()


class SummaryResult(BaseModel):
    """Structured summary generated from conversation"""

    summary: str

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, v: str) -> str:
        """Ensure summary is not empty and reasonable length"""
        v = v.strip()
        if not v:
            raise ValueError("Summary cannot be empty")
        if len(v) < 20:
            raise ValueError("Summary is too short (minimum 20 characters)")
        return v
