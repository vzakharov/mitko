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
        """Generate match rationale using all three profile parts"""

        # Build profile sections, handling null values during lazy migration
        seeker_profile = f"""Technical Background: {seeker.matching_summary or "Not provided"}
Work Preferences: {seeker.practical_context or "Not yet specified"}
Internal Notes: {seeker.private_observations or "None"}"""

        provider_profile = f"""Technical Background: {provider.matching_summary or "Not provided"}
Work Preferences: {provider.practical_context or "Not yet specified"}
Internal Notes: {provider.private_observations or "None"}"""

        prompt = dedent(
            f"""Analyze these two profiles and explain why they're a good match:

            Seeker Profile:
            {seeker_profile}

            Provider Profile:
            {provider_profile}

            Generate a structured match rationale considering:
            - Technical alignment (skills, experience, domain expertise)
            - Practical compatibility (location, remote preference, availability) - if specified
            - Potential concerns from internal notes (if any - use these to inform confidence scoring)

            Important: Internal notes are for YOUR evaluation only. Do not mention them explicitly in the
            explanation shown to users. If they raise concerns, reflect that in a lower confidence_score
            and focus on genuine alignments in your explanation.

            Note: Work Preferences may be "Not yet specified" for some users during a transition period.
            Focus on technical alignment in such cases.

            Output:
            - explanation: A brief, friendly 2-3 sentence explanation of technical + practical fit
            - key_alignments: A list of 2-4 specific points where they align (focus on technical if practical missing)
            - confidence_score: A score from 0.0 to 1.0 (adjust down if internal notes raise concerns or if practical context is missing)"""
        )

        result = await RATIONALE_AGENT.run(prompt)
        rationale = result.output

        # Format for display (only explanation and key_alignments are shown to users)
        formatted = [rationale.explanation]
        if rationale.key_alignments:
            formatted.append("\n\nKey alignments:")
            for alignment in rationale.key_alignments:
                formatted.append(f"\n• {alignment}")

        return "".join(formatted)
