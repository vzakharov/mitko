"""Return types for match finding operations."""

from dataclasses import dataclass

from ..models import Match


class MatchResult:
    """Base class for match finding results."""


@dataclass
class MatchFound(MatchResult):
    """A match was found (real match or participation record)."""

    match: Match


@dataclass
class RoundExhausted(MatchResult):
    """Current round exhausted, all users have participated."""

    current_round: int


@dataclass
class AllUsersMatched(MatchResult):
    """No complete users exist at all."""

    pass
