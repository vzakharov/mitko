from sqlalchemy import Float, and_, or_, select
from sqlalchemy import func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..config import SETTINGS
from ..models import Match, User
from .match_result import (
    AllUsersMatched,
    MatchFound,
    MatchResult,
    RoundExhausted,
)


class MatcherService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_next_match_pair(
        self, forced_round: int | None = None
    ) -> MatchResult:
        """Find next match pair using round-robin algorithm.

        Round-robin logic:
        - Current round = MAX(matching_round) from matches table (or 1 if no matches exist)
        - Selects user_a who hasn't been user_a in current round yet (ordered by profile_updated_at)
        - Selects user_b who has never been matched with user_a before (ordered by similarity)
        - When all users participated in current round, scheduler advances to next round
        - user_b does not track rounds (passive selection by similarity)

        Returns:
            - MatchFound: Match created (real match or participation record)
            - RoundExhausted: Current round complete, needs advancement
            - AllUsersMatched: No unmatched users exist

        Returns Match WITHOUT rationale (empty string) - rationale generation
        deferred to MatchGeneration. Match is NOT committed - caller decides
        when to commit.
        """
        current_round = forced_round or await self._get_current_round()
        users_already_tried_in_round = await self._get_users_already_tried_in_round(
            current_round
        )

        user_a = await self._find_next_user_a(
            exclude_users=set(users_already_tried_in_round)
        )

        if user_a is None:
            if users_already_tried_in_round:
                return RoundExhausted(current_round=current_round)

            return AllUsersMatched()

        if user_a.is_seeker:
            similar_users = await self._find_similar_users(
                user_a, target_role="provider"
            )
        elif user_a.is_provider:
            similar_users = await self._find_similar_users(
                user_a, target_role="seeker"
            )
        else:
            raise ValueError(
                f"User {user_a.telegram_id} has neither seeker nor provider role - "
                f"this should be prevented by _find_next_user_a() query filters"
            )

        if not similar_users:
            match = Match(
                user_a_id=user_a.telegram_id,
                user_b_id=None,
                similarity_score=0.0,
                match_rationale="",
                status="unmatched",
                matching_round=current_round,
            )
            self.session.add(match)
            return MatchFound(match=match)

        user_b, similarity = similar_users[0]

        match = Match(
            user_a_id=user_a.telegram_id,
            user_b_id=user_b.telegram_id,
            similarity_score=similarity,
            match_rationale="",
            status="pending",
            matching_round=current_round,
        )
        self.session.add(match)

        return MatchFound(match=match)

    async def _get_current_round(self) -> int:
        """Get the current matching round (MAX round from matches table, or 1 if empty)."""
        return (
            await self.session.execute(
                select(sql_func.max(Match.matching_round))
            )
        ).scalar_one_or_none() or 1

    async def _get_users_already_tried_in_round(
        self, current_round: int
    ) -> list[int]:
        """Get list of user IDs who have already been user_a in the current round."""
        return [
            id
            for (id,) in await self.session.execute(
                select(col(Match.user_a_id))
                .where(col(Match.matching_round) == current_round)
                .distinct()
            )
        ]

    async def advance_round(self) -> int:
        """Advance to next matching round.

        Returns:
            The new round number.
        """
        current_round = await self._get_current_round()
        return current_round + 1

    async def _find_next_user_a(self, exclude_users: set[int]) -> User | None:
        query_conditions = [
            col(User.is_complete) == True,  # noqa: E712
            col(User.embedding) != None,  # noqa: E711
            or_(
                col(User.is_seeker) == True,  # noqa: E712
                col(User.is_provider) == True,  # noqa: E712
            ),
        ]

        if exclude_users:
            query_conditions.append(col(User.telegram_id).not_in(exclude_users))

        result = await self.session.execute(
            select(User)
            .where(and_(*query_conditions))
            .order_by(col(User.profile_updated_at).asc().nulls_last())
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def _find_similar_users(
        self, source_user: User, target_role: str
    ) -> list[tuple[User, float]]:
        """Find similar users with specified role (role-agnostic version).

        Args:
            source_user: User to find matches for
            target_role: 'seeker' or 'provider'

        Returns:
            List of (user, similarity) tuples, excluding users already matched with source_user
        """
        if source_user.embedding is None:
            return []

        # Get user IDs already matched with source_user (as user_a or user_b)
        already_matched_ids = [
            id
            for (id,) in await self.session.execute(
                select(col(Match.user_b_id))
                .where(col(Match.user_a_id) == source_user.telegram_id)
                .where(col(Match.user_b_id) != None)  # noqa: E711
                .union(
                    select(col(Match.user_a_id)).where(
                        col(Match.user_b_id) == source_user.telegram_id
                    )
                )
            )
        ]

        distance = col(User.embedding).op("<=>", return_type=Float())(
            source_user.embedding
        )
        similarity_expr = (1 - distance).label("similarity")

        # Build role condition
        if target_role == "provider":
            role_condition = col(User.is_provider) == True  # noqa: E712
        elif target_role == "seeker":
            role_condition = col(User.is_seeker) == True  # noqa: E712
        else:
            raise ValueError(f"Invalid target_role: {target_role}")

        query_conditions = [
            role_condition,
            col(User.is_complete) == True,  # noqa: E712
            col(User.embedding) != None,  # noqa: E711
            col(User.telegram_id) != source_user.telegram_id,
            similarity_expr >= SETTINGS.similarity_threshold,
        ]

        if already_matched_ids:
            query_conditions.append(
                col(User.telegram_id).not_in(already_matched_ids)
            )

        return [
            (user, float(similarity))
            for user, similarity in await self.session.execute(
                select(User, similarity_expr)
                .where(and_(*query_conditions))
                .order_by(similarity_expr.desc())
                .limit(1)
            )
        ]
