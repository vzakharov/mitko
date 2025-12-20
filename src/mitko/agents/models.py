"""Pydantic models for structured LLM outputs"""

from pydantic import BaseModel, field_validator, model_validator
from typing import Any


class ProfileData(BaseModel):
    """Structured profile data extracted from conversation"""

    is_seeker: bool
    is_provider: bool
    summary: str

    @model_validator(mode="after")
    def validate_roles(self) -> "ProfileData":
        """Ensure at least one role is enabled"""
        if not (self.is_seeker or self.is_provider):
            raise ValueError("Profile must have at least one role enabled (is_seeker or is_provider)")
        return self

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, v: str) -> str:
        """Ensure summary is not empty"""
        if not v or not v.strip():
            raise ValueError("Summary cannot be empty")
        return v.strip()


class MatchRationale(BaseModel):
    """Structured match rationale with explanation"""

    explanation: str
    key_alignments: list[str]
    confidence_score: float

    @field_validator("explanation")
    @classmethod
    def validate_explanation(cls, v: str) -> str:
        """Ensure explanation is not empty"""
        if not v or not v.strip():
            raise ValueError("Explanation cannot be empty")
        return v.strip()

    @field_validator("key_alignments")
    @classmethod
    def validate_alignments(cls, v: list[str]) -> list[str]:
        """Ensure at least one alignment point"""
        if not v:
            raise ValueError("Must provide at least one key alignment")
        return [item.strip() for item in v if item.strip()]

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is between 0 and 1"""
        if not 0 <= v <= 1:
            raise ValueError("Confidence score must be between 0 and 1")
        return v


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
