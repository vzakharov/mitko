from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import Float, Select, and_, or_, select
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


@dataclass
class MatcherService:
    session: AsyncSession

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
        users_already_tried_in_round = (
            await self._get_users_already_tried_in_round(current_round)
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
            latest_profile_updated_at=self._compute_latest_profile_updated_at(
                user_a, user_b
            ),
        )
        self.session.add(match)

        return MatchFound(match=match)

    async def advance_round(self) -> int:
        """Advance to next matching round.

        Returns:
            The new round number.
        """
        return await self._get_current_round() + 1

    def _build_match_exclusion_query(
        self,
        source_user: User,
        select_col: int | None,
        source_match_col: int | None,
    ) -> Select[tuple[int | None]]:
        """Build query to find users already matched with source_user in one direction.

        Args:
            source_user: User to find historical matches for
            select_col: Column to select and join on (e.g., Match.user_b_id or Match.user_a_id)
            source_match_col: Match column that should equal source_user's ID

        Returns:
            Select query that returns user IDs to exclude from matching
        """
        return (
            select(col(select_col))
            .join(User, col(User.telegram_id) == col(select_col))
            .where(col(source_match_col) == source_user.telegram_id)
            .where(
                or_(
                    col(Match.status) != "disqualified",
                    col(Match.latest_profile_updated_at)
                    >= sql_func.greatest(
                        col(User.profile_updated_at),
                        source_user.profile_updated_at or datetime.now(),
                    ),
                )
            )
        )

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

    def _compute_latest_profile_updated_at(
        self, user_a: User, user_b: User
    ) -> datetime | None:
        """Compute the latest profile update timestamp between two matched users.

        Args:
            user_a: First user
            user_b: Second user

        Returns:
            The most recent profile_updated_at timestamp, or None if either user has no profile_updated_at
        """
        return (
            max(user_a.profile_updated_at, user_b.profile_updated_at)
            if user_a.profile_updated_at and user_b.profile_updated_at
            else user_a.profile_updated_at or user_b.profile_updated_at
        )

    async def _find_next_user_a(self, exclude_users: set[int]) -> User | None:
        query_conditions = [
            col(User.is_complete).is_(True),
            col(User.embedding).isnot(None),
            or_(
                col(User.is_seeker).is_(True),
                col(User.is_provider).is_(True),
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
        self, source_user: User, target_role: Literal["seeker", "provider"]
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

        similarity_expr = (
            1
            - col(User.embedding).op("<=>", return_type=Float())(
                source_user.embedding
            )
        ).label("similarity")

        return [
            (user, float(similarity))
            for user, similarity in await self.session.execute(
                select(User, similarity_expr)
                .where(
                    and_(
                        col(
                            {
                                "provider": User.is_provider,
                                "seeker": User.is_seeker,
                            }[target_role]
                        ).is_(True),
                        col(User.is_complete).is_(True),
                        col(User.embedding).isnot(None),
                        col(User.telegram_id) != source_user.telegram_id,
                        similarity_expr >= SETTINGS.similarity_threshold,
                        col(User.telegram_id).not_in(
                            # Get user IDs already matched with source_user, excluding those eligible for re-matching.
                            # Re-matching is ONLY allowed when BOTH conditions are true:
                            # 1. Match status IS "disqualified" (LLM rejected), AND
                            # 2. At least one user updated their profile since the match
                            #
                            # Therefore, exclude users where:
                            # - Status is NOT "disqualified", OR
                            # - Neither user has updated profile since match (even if disqualified)
                            self._build_match_exclusion_query(
                                source_user, Match.user_b_id, Match.user_a_id
                            ).union(
                                self._build_match_exclusion_query(
                                    source_user,
                                    Match.user_a_id,
                                    Match.user_b_id,
                                )
                            )
                        ),
                    )
                )
                .order_by(similarity_expr.desc())
                .limit(1)
            )
        ]
