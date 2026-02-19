"""Test MatcherService — the core matching algorithm.

Tests the complex SQL queries that determine:
- Which user gets matched next (round-robin, pending-match blocking)
- Which users are excluded from re-matching
- When rounds are exhausted vs. no users exist at all

Note: _find_similar_users() uses pgvector operators not available in SQLite,
so we mock it and test _find_next_user_a() + find_next_match_pair() orchestration
against real SQL.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mitko.models.match import Match, MatchStatus
from mitko.models.user import User, UserState
from mitko.services.match_result import (
    AllUsersMatched,
    MatchFound,
    RoundExhausted,
)
from mitko.services.matcher import MatcherService

# --- Helpers ---


async def _create_user(
    session: AsyncSession,
    telegram_id: int,
    *,
    is_seeker: bool = False,
    is_provider: bool = False,
    state: UserState = "active",
    has_embedding: bool = True,
) -> User:
    user = User(
        telegram_id=telegram_id,
        is_seeker=is_seeker,
        is_provider=is_provider,
        state=state,
        embedding=[0.1] * 1536 if has_embedding else None,
    )
    session.add(user)
    await session.flush()
    return user


async def _create_match(
    session: AsyncSession,
    user_a_id: int,
    user_b_id: int | None,
    *,
    status: MatchStatus = "pending",
    matching_round: int = 1,
    latest_profile_updated_at: datetime | None = None,
) -> Match:
    match = Match(
        user_a_id=user_a_id,
        user_b_id=user_b_id,
        similarity_score=0.85,
        match_rationale="",
        status=status,
        matching_round=matching_round,
        latest_profile_updated_at=latest_profile_updated_at,
    )
    session.add(match)
    await session.flush()
    return match


def _mock_similar_users(user: User, similarity: float = 0.9) -> AsyncMock:
    """Create a mock for _find_similar_users that returns the given user."""
    mock = AsyncMock(return_value=[(user, similarity)])
    return mock


def _mock_no_similar_users() -> AsyncMock:
    return AsyncMock(return_value=[])


# --- No users at all ---


async def test_no_users_returns_all_users_matched(db_session: AsyncSession):
    result = await MatcherService(db_session).find_next_match_pair()
    assert isinstance(result, AllUsersMatched)


# --- Single user, no candidates ---


async def test_single_user_no_candidates(db_session: AsyncSession):
    """Single seeker with no providers → participation record (unmatched)."""
    await _create_user(db_session, 1001, is_seeker=True)

    with patch.object(
        MatcherService, "_find_similar_users", _mock_no_similar_users()
    ):
        result = await MatcherService(db_session).find_next_match_pair()

    assert isinstance(result, MatchFound)
    assert result.match.user_b_id is None
    assert result.match.status == "unmatched"


# --- Two users, successful match ---


async def test_seeker_provider_match(db_session: AsyncSession):
    """Seeker + provider → match found with pending status."""
    await _create_user(db_session, 2001, is_seeker=True)
    provider = await _create_user(db_session, 2002, is_provider=True)

    with patch.object(
        MatcherService,
        "_find_similar_users",
        _mock_similar_users(provider),
    ):
        result = await MatcherService(db_session).find_next_match_pair()

    assert isinstance(result, MatchFound)
    assert result.match.user_a_id == 2001
    assert result.match.user_b_id == 2002
    assert result.match.status == "pending"


# --- Round-robin: all users tried → RoundExhausted ---


async def test_round_exhausted_when_all_tried(db_session: AsyncSession):
    """When all users already participated in the round → RoundExhausted."""
    seeker = await _create_user(db_session, 3001, is_seeker=True)
    provider = await _create_user(db_session, 3002, is_provider=True)

    # Both users already participated in round 1
    await _create_match(
        db_session,
        seeker.telegram_id,
        None,
        status="unmatched",
        matching_round=1,
    )
    await _create_match(
        db_session,
        provider.telegram_id,
        None,
        status="unmatched",
        matching_round=1,
    )

    result = await MatcherService(db_session).find_next_match_pair()
    assert isinstance(result, RoundExhausted)
    assert result.current_round == 1


# --- _find_next_user_a filtering ---


async def test_inactive_user_excluded(db_session: AsyncSession):
    """Users with state != 'active' are excluded from matching."""
    await _create_user(db_session, 4001, is_seeker=True, state="onboarding")

    result = await MatcherService(db_session).find_next_match_pair()
    assert isinstance(result, AllUsersMatched)


async def test_user_without_embedding_excluded(db_session: AsyncSession):
    """Users without embeddings are excluded from matching."""
    await _create_user(db_session, 5001, is_seeker=True, has_embedding=False)

    result = await MatcherService(db_session).find_next_match_pair()
    assert isinstance(result, AllUsersMatched)


async def test_user_without_role_excluded(db_session: AsyncSession):
    """Users with no role (neither seeker nor provider) are excluded."""
    await _create_user(db_session, 6001, state="active")

    result = await MatcherService(db_session).find_next_match_pair()
    assert isinstance(result, AllUsersMatched)


# --- Pending match blocking ---


async def test_user_with_qualified_match_blocked(db_session: AsyncSession):
    """User with an unanswered 'qualified' match can't be user_a."""
    seeker = await _create_user(db_session, 7001, is_seeker=True)
    provider = await _create_user(db_session, 7002, is_provider=True)
    third = await _create_user(db_session, 7003, is_provider=True)

    # Seeker and provider have a qualified match (both blocked)
    # The match also makes seeker "already tried" in round 1
    await _create_match(
        db_session, seeker.telegram_id, provider.telegram_id, status="qualified"
    )

    # Only third user is eligible — should be picked as user_a
    with patch.object(
        MatcherService, "_find_similar_users", _mock_no_similar_users()
    ):
        result = await MatcherService(db_session).find_next_match_pair()

    assert isinstance(result, MatchFound)
    assert result.match.user_a_id == third.telegram_id
    # seeker and provider are both blocked by the qualified match
    assert result.match.user_a_id not in (
        seeker.telegram_id,
        provider.telegram_id,
    )


async def test_user_awaiting_response_blocked(db_session: AsyncSession):
    """User B who hasn't responded to A's acceptance is blocked from being user_a."""
    user_a = await _create_user(db_session, 8001, is_seeker=True)
    user_b = await _create_user(db_session, 8002, is_provider=True)

    # user_a accepted, waiting for user_b's response
    # This also marks user_a as "tried" in round 1
    await _create_match(
        db_session, user_a.telegram_id, user_b.telegram_id, status="a_accepted"
    )

    # user_b hasn't responded → blocked by pending match check
    # user_a already tried in round 1 → excluded by round-robin
    # → nobody left → RoundExhausted
    result = await MatcherService(db_session).find_next_match_pair()
    assert isinstance(result, RoundExhausted)


async def test_user_who_accepted_not_blocked(db_session: AsyncSession):
    """User who already accepted is NOT blocked — only the non-responder is."""
    user_a = await _create_user(db_session, 9001, is_seeker=True)
    user_b = await _create_user(db_session, 9002, is_provider=True)

    # user_b accepted first, now waiting for user_a's response
    await _create_match(
        db_session, user_a.telegram_id, user_b.telegram_id, status="b_accepted"
    )

    # user_a: tried in round 1 (match record) AND blocked (hasn't responded)
    # user_b: NOT tried, NOT blocked (already accepted)
    # → user_b should be picked as user_a
    with patch.object(
        MatcherService, "_find_similar_users", _mock_no_similar_users()
    ):
        result = await MatcherService(db_session).find_next_match_pair()

    assert isinstance(result, MatchFound)
    assert result.match.user_a_id == user_b.telegram_id


# --- Round-robin fairness ---


@pytest.mark.parametrize(
    "profile_updated_ats",
    [
        pytest.param(
            [
                datetime(2025, 1, 1),
                datetime(2025, 1, 2),
            ],
            id="oldest_profile_first",
        ),
    ],
)
async def test_round_robin_picks_oldest_updated_first(
    db_session: AsyncSession,
    profile_updated_ats: list[datetime],
):
    """Users are picked in order of profile_updated_at (oldest first)."""
    user_old = await _create_user(db_session, 10001, is_seeker=True)
    user_old.profile_updated_at = profile_updated_ats[0]

    user_new = await _create_user(db_session, 10002, is_seeker=True)
    user_new.profile_updated_at = profile_updated_ats[1]

    await _create_user(db_session, 10003, is_provider=True)
    await db_session.flush()

    with patch.object(
        MatcherService, "_find_similar_users", _mock_no_similar_users()
    ):
        result = await MatcherService(db_session).find_next_match_pair()

    assert isinstance(result, MatchFound)
    assert result.match.user_a_id == user_old.telegram_id


# --- Re-matching logic (exclusion query) ---


async def test_exclusion_allows_rematching_when_disqualified_and_profile_updated(
    db_session: AsyncSession,
):
    """Exclusion query allows re-matching if disqualified + at least one profile updated."""
    user_a = await _create_user(db_session, 20001, is_seeker=True)
    user_a.profile_updated_at = datetime(2025, 1, 1)

    user_b = await _create_user(db_session, 20002, is_provider=True)
    user_b.profile_updated_at = datetime(2025, 1, 1)

    # Create disqualified match with latest_profile_updated_at BEFORE recent update
    await _create_match(
        db_session,
        user_a.telegram_id,
        user_b.telegram_id,
        status="disqualified",
        latest_profile_updated_at=datetime(2024, 12, 31),
    )

    # Update user_b's profile AFTER the match
    user_b.profile_updated_at = datetime(2025, 1, 5)
    await db_session.flush()

    # Build exclusion query (user_b_id where user_a_id = user_a)
    from mitko.models.match import Match

    exclusion_query = MatcherService(db_session)._build_match_exclusion_query(  # pyright: ignore[reportPrivateUsage]
        user_a, Match.user_b_id, Match.user_a_id
    )

    excluded_ids = [id for (id,) in await db_session.execute(exclusion_query)]

    # user_b should NOT be in the exclusion list (re-matching allowed)
    assert user_b.telegram_id not in excluded_ids


async def test_exclusion_blocks_rematching_when_disqualified_but_no_update(
    db_session: AsyncSession,
):
    """Exclusion query blocks re-matching if disqualified but no profile updates."""
    user_a = await _create_user(db_session, 20101, is_seeker=True)
    user_a.profile_updated_at = datetime(2025, 1, 1)

    user_b = await _create_user(db_session, 20102, is_provider=True)
    user_b.profile_updated_at = datetime(2025, 1, 1)

    # Create disqualified match with latest_profile_updated_at EQUAL to both users
    await _create_match(
        db_session,
        user_a.telegram_id,
        user_b.telegram_id,
        status="disqualified",
        latest_profile_updated_at=datetime(2025, 1, 1),
    )

    await db_session.flush()

    from mitko.models.match import Match

    exclusion_query = MatcherService(db_session)._build_match_exclusion_query(  # pyright: ignore[reportPrivateUsage]
        user_a, Match.user_b_id, Match.user_a_id
    )

    excluded_ids = [id for (id,) in await db_session.execute(exclusion_query)]

    # user_b SHOULD be in the exclusion list (no updates, no re-matching)
    assert user_b.telegram_id in excluded_ids


async def test_exclusion_always_blocks_rejected_matches(
    db_session: AsyncSession,
):
    """Exclusion query always blocks user-rejected matches, even with profile updates."""
    user_a = await _create_user(db_session, 20201, is_seeker=True)
    user_a.profile_updated_at = datetime(2025, 1, 1)

    user_b = await _create_user(db_session, 20202, is_provider=True)
    user_b.profile_updated_at = datetime(2025, 1, 1)

    # Create rejected match
    await _create_match(
        db_session,
        user_a.telegram_id,
        user_b.telegram_id,
        status="rejected",
        latest_profile_updated_at=datetime(2024, 12, 31),
    )

    # Update both profiles AFTER the match
    user_a.profile_updated_at = datetime(2025, 1, 5)
    user_b.profile_updated_at = datetime(2025, 1, 5)
    await db_session.flush()

    from mitko.models.match import Match

    exclusion_query = MatcherService(db_session)._build_match_exclusion_query(  # pyright: ignore[reportPrivateUsage]
        user_a, Match.user_b_id, Match.user_a_id
    )

    excluded_ids = [id for (id,) in await db_session.execute(exclusion_query)]

    # user_b SHOULD be excluded (status != disqualified)
    assert user_b.telegram_id in excluded_ids


async def test_exclusion_always_blocks_connected_matches(
    db_session: AsyncSession,
):
    """Exclusion query always blocks connected matches, even with profile updates."""
    user_a = await _create_user(db_session, 20301, is_seeker=True)
    user_a.profile_updated_at = datetime(2025, 1, 1)

    user_b = await _create_user(db_session, 20302, is_provider=True)
    user_b.profile_updated_at = datetime(2025, 1, 1)

    # Create connected match
    await _create_match(
        db_session,
        user_a.telegram_id,
        user_b.telegram_id,
        status="connected",
        latest_profile_updated_at=datetime(2024, 12, 31),
    )

    # Update both profiles AFTER the match
    user_a.profile_updated_at = datetime(2025, 1, 5)
    user_b.profile_updated_at = datetime(2025, 1, 5)
    await db_session.flush()

    from mitko.models.match import Match

    exclusion_query = MatcherService(db_session)._build_match_exclusion_query(  # pyright: ignore[reportPrivateUsage]
        user_a, Match.user_b_id, Match.user_a_id
    )

    excluded_ids = [id for (id,) in await db_session.execute(exclusion_query)]

    # user_b SHOULD be excluded (status != disqualified)
    assert user_b.telegram_id in excluded_ids
