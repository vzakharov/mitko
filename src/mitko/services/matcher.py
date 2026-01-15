from textwrap import dedent

from sqlalchemy import Float, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..agents.rationale_agent import RATIONALE_AGENT
from ..config import SETTINGS
from ..models import Match, User


class MatcherService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_matches(self) -> list[Match]:
        seeker_users = await self.session.execute(
            select(User).where(
                and_(
                    col(User.is_seeker) == True,  # noqa: E712
                    col(User.is_complete) == True,  # noqa: E712
                    col(User.embedding) != None,  # noqa: E711
                )
            )
        )
        seekers = seeker_users.scalars().all()

        matches_created = list[Match]()
        for seeker in seekers:
            provider_matches = await self._find_similar_providers(seeker)
            for provider, similarity in provider_matches:
                if await self._should_create_match(
                    seeker.telegram_id, provider.telegram_id
                ):
                    match = await self._create_match(
                        seeker, provider, similarity
                    )
                    matches_created.append(match)

        await self.session.commit()
        return matches_created

    async def _find_similar_providers(
        self, seeker: User
    ) -> list[tuple[User, float]]:
        if seeker.embedding is None:
            return []

        # Calculate similarity using pgvector's cosine_distance operator (<=>)
        # Returns distance (0 = identical, higher = less similar)
        # Convert to similarity: 1 - distance (1 = identical, 0 = opposite)
        distance = col(User.embedding).op("<=>", return_type=Float())(
            seeker.embedding
        )
        similarity_expr = (1 - distance).label("similarity")

        query = (
            select(User, similarity_expr)
            .where(
                and_(
                    col(User.is_provider) == True,  # noqa: E712
                    col(User.is_complete) == True,  # noqa: E712
                    col(User.embedding) != None,  # noqa: E711
                    col(User.telegram_id) != seeker.telegram_id,
                    similarity_expr >= SETTINGS.similarity_threshold,
                )
            )
            .order_by(similarity_expr.desc())
            .limit(SETTINGS.max_matches_per_profile)
        )

        result = await self.session.execute(query)
        return [(user, float(similarity)) for user, similarity in result]

    async def _should_create_match(
        self, user_a_id: int, user_b_id: int
    ) -> bool:
        existing = await self.session.execute(
            select(Match).where(
                or_(
                    and_(
                        col(Match.user_a_id) == user_a_id,
                        col(Match.user_b_id) == user_b_id,
                    ),
                    and_(
                        col(Match.user_a_id) == user_b_id,
                        col(Match.user_b_id) == user_a_id,
                    ),
                )
            )
        )
        return existing.scalar_one_or_none() is None

    async def _create_match(
        self, seeker: User, provider: User, similarity: float
    ) -> Match:
        rationale = await self._generate_match_rationale(seeker, provider)

        match = Match(
            user_a_id=seeker.telegram_id,
            user_b_id=provider.telegram_id,
            similarity_score=similarity,
            match_rationale=rationale,
            status="pending",
        )
        self.session.add(match)
        return match

    async def _generate_match_rationale(
        self, seeker: User, provider: User
    ) -> str:
        prompt = dedent(
            f"""Analyze these two profiles and explain why they're a good match:

            Seeker Profile:
            {seeker.summary or ""}

            Provider Profile:
            {provider.summary or ""}

            Generate a structured match rationale with:
            - explanation: A brief, friendly 2-3 sentence explanation
            - key_alignments: A list of 2-4 specific points where they align
            - confidence_score: A score from 0.0 to 1.0 (where 1.0 is a perfect match)"""
        )

        result = await RATIONALE_AGENT.run(prompt)
        rationale = result.output

        message_parts = [rationale.explanation]
        if rationale.key_alignments:
            message_parts.append("\n\nKey alignments:")
            for alignment in rationale.key_alignments:
                message_parts.append(f"• {alignment}")

        return "".join(message_parts)
