from sqlalchemy import Float, and_, or_, select
from sqlalchemy import func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..config import SETTINGS
from ..models import Match, User


class MatcherService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_current_round(self) -> int:
        """Get the current matching round (MAX round from matches table, or 1 if empty)."""
        result = await self.session.execute(
            select(sql_func.max(Match.matching_round))
        )
        max_round = result.scalar_one_or_none()
        return max_round if max_round is not None else 1

    async def _get_users_in_round(self, current_round: int) -> list[int]:
        """Get list of user IDs who have already been user_a in the current round."""
        result = await self.session.execute(
            select(col(Match.user_a_id))
            .where(col(Match.matching_round) == current_round)
            .distinct()
        )
        return [row[0] for row in result]

    async def find_next_match_pair(self) -> Match | None:
        """Find next match pair: earliest updated user (not yet in current round) + most similar opposite-role user (never matched before).

        Round-robin logic:
        - Current round = MAX(matching_round) from matches table (or 1 if no matches exist)
        - Selects user_a who hasn't been user_a in current round yet (ordered by profile_updated_at)
        - Selects user_b who has never been matched with user_a before (ordered by similarity)
        - When all users participated in current round, auto-advances to next round
        - user_b does not track rounds (passive selection by similarity)

        Returns Match WITHOUT rationale (empty string) - rationale generation deferred to MatchGeneration.
        Match is NOT committed - caller decides when to commit.
        """
        # Get current round
        current_round = await self._get_current_round()

        # Get users who already participated in current round (as user_a)
        users_in_round = await self._get_users_in_round(current_round)

        # Find earliest user NOT in current round yet
        query_conditions = [
            col(User.is_complete) == True,  # noqa: E712
            col(User.embedding) != None,  # noqa: E711
            or_(
                col(User.is_seeker) == True,  # noqa: E712
                col(User.is_provider) == True,  # noqa: E712
            ),
        ]

        if users_in_round:
            query_conditions.append(
                col(User.telegram_id).not_in(users_in_round)
            )

        earliest_user_result = await self.session.execute(
            select(User)
            .where(and_(*query_conditions))
            .order_by(col(User.profile_updated_at).asc().nulls_last())
            .limit(1)
        )
        user_a = earliest_user_result.scalar_one_or_none()

        if user_a is None:
            # All users participated in current round - advance to next round
            if users_in_round:
                # Advance to next round (regardless of whether current round had real matches)
                current_round += 1
                # Retry selection with round+1 (users_in_round will be empty for round+1)
                earliest_user_result = await self.session.execute(
                    select(User)
                    .where(
                        and_(
                            col(User.is_complete) == True,  # noqa: E712
                            col(User.embedding) != None,  # noqa: E711
                            or_(
                                col(User.is_seeker) == True,  # noqa: E712
                                col(User.is_provider) == True,  # noqa: E712
                            ),
                        )
                    )
                    .order_by(col(User.profile_updated_at).asc().nulls_last())
                    .limit(1)
                )
                user_a = earliest_user_result.scalar_one_or_none()

                if user_a is None:
                    # No complete users exist at all
                    return None
            else:
                # No users in round and no user_a found - no complete users exist
                return None

        # Find most similar user on opposite side (excludes previously matched users)
        if user_a.is_seeker:
            similar_users = await self._find_similar_users(
                user_a, target_role="provider"
            )
        elif user_a.is_provider:
            similar_users = await self._find_similar_users(
                user_a, target_role="seeker"
            )
        else:
            return None

        if not similar_users:
            # No new matches available for user_a (all potential matches already matched or below threshold)
            # Mark user_a as having participated in this round (even though no match was created)
            # This prevents infinite loops where an unmatchable user blocks the round
            match = Match(
                user_a_id=user_a.telegram_id,
                user_b_id=None,
                similarity_score=0.0,
                match_rationale="",
                status="unmatched",
                matching_round=current_round,
            )
            self.session.add(match)
            return match

        user_b, similarity = similar_users[0]

        # No need for _should_create_match() - already filtered in _find_similar_users()

        # Create match WITHOUT rationale (deferred to generation)
        match = Match(
            user_a_id=user_a.telegram_id,
            user_b_id=user_b.telegram_id,
            similarity_score=similarity,
            match_rationale="",
            status="pending",
            matching_round=current_round,
        )
        self.session.add(match)

        return match

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
        existing_matches = await self.session.execute(
            select(col(Match.user_b_id))
            .where(col(Match.user_a_id) == source_user.telegram_id)
            .where(col(Match.user_b_id) != None)  # noqa: E711
            .union(
                select(col(Match.user_a_id)).where(
                    col(Match.user_b_id) == source_user.telegram_id
                )
            )
        )
        already_matched_ids = [row[0] for row in existing_matches]

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

        query = (
            select(User, similarity_expr)
            .where(and_(*query_conditions))
            .order_by(similarity_expr.desc())
            .limit(1)
        )

        result = await self.session.execute(query)
        return [(user, float(similarity)) for user, similarity in result]
