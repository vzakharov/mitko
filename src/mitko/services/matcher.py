from textwrap import dedent

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..agents import RationaleAgent, get_model_name
from ..config import settings
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

        matches_created = []
        for seeker in seekers:
            provider_matches = await self._find_similar_providers(seeker)
            for provider, similarity in provider_matches:
                if await self._should_create_match(seeker.telegram_id, provider.telegram_id):
                    match = await self._create_match(seeker, provider, similarity)
                    matches_created.append(match)

        await self.session.commit()
        return matches_created

    async def _find_similar_providers(
        self, seeker: User
    ) -> list[tuple[User, float]]:
        if not seeker.embedding:
            return []

        embedding_str = "[" + ",".join(str(x) for x in seeker.embedding) + "]"

        query = text(dedent("""
            SELECT u.telegram_id, 1 - (u.embedding <=> :seeker_embedding::vector) as similarity
            FROM users u
            WHERE u.is_provider = true
            AND u.is_complete = true
            AND u.embedding IS NOT NULL
            AND u.telegram_id != :seeker_id
            AND 1 - (u.embedding <=> :seeker_embedding::vector) >= :threshold
            ORDER BY similarity DESC
            LIMIT :limit
        """))

        result = await self.session.execute(
            query,
            {
                "seeker_embedding": embedding_str,
                "seeker_id": seeker.telegram_id,
                "threshold": settings.similarity_threshold,
                "limit": settings.max_matches_per_profile,
            },
        )

        matches = []
        for row in result:
            user = await self.session.get(User, row.telegram_id)
            if user:
                matches.append((user, float(row.similarity)))
        return matches

    async def _should_create_match(self, user_a_id: int, user_b_id: int) -> bool:
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

    async def _generate_match_rationale(self, seeker: User, provider: User) -> str:
        rationale_agent = RationaleAgent(get_model_name())
        rationale = await rationale_agent.generate_rationale(
            seeker_summary=seeker.summary or "",
            provider_summary=provider.summary or "",
        )

        message_parts = [rationale.explanation]
        if rationale.key_alignments:
            message_parts.append("\n\nKey alignments:")
            for alignment in rationale.key_alignments:
                message_parts.append(f"• {alignment}")

        return "".join(message_parts)

