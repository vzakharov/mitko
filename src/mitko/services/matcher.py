from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
import uuid

from ..models import Profile, Match, MatchStatus
from ..llm import LLMProvider
from ..config import settings


class MatcherService:
    def __init__(self, session: AsyncSession, llm: LLMProvider) -> None:
        self.session = session
        self.llm = llm

    async def find_matches(self) -> list[Match]:
        seeker_profiles = await self.session.execute(
            select(Profile).where(
                and_(
                    Profile.role == "seeker",
                    Profile.is_complete == True,
                    Profile.embedding.isnot(None),
                )
            )
        )
        seekers = seeker_profiles.scalars().all()

        matches_created = []
        for seeker in seekers:
            provider_matches = await self._find_similar_providers(seeker)
            for provider, similarity in provider_matches:
                if await self._should_create_match(seeker.id, provider.id):
                    match = await self._create_match(seeker, provider, similarity)
                    matches_created.append(match)

        await self.session.commit()
        return matches_created

    async def _find_similar_providers(
        self, seeker: Profile
    ) -> list[tuple[Profile, float]]:
        if not seeker.embedding:
            return []

        embedding_str = "[" + ",".join(str(x) for x in seeker.embedding) + "]"

        query = text("""
            SELECT p.id, 1 - (p.embedding <=> :seeker_embedding::vector) as similarity
            FROM profiles p
            WHERE p.role = 'provider'
            AND p.is_complete = true
            AND p.embedding IS NOT NULL
            AND p.id != :seeker_id
            AND 1 - (p.embedding <=> :seeker_embedding::vector) >= :threshold
            ORDER BY similarity DESC
            LIMIT :limit
        """)

        result = await self.session.execute(
            query,
            {
                "seeker_embedding": embedding_str,
                "seeker_id": str(seeker.id),
                "threshold": settings.similarity_threshold,
                "limit": settings.max_matches_per_profile,
            },
        )

        matches = []
        for row in result:
            profile = await self.session.get(Profile, uuid.UUID(row.id))
            if profile:
                matches.append((profile, float(row.similarity)))
        return matches

    async def _should_create_match(self, profile_a_id: uuid.UUID, profile_b_id: uuid.UUID) -> bool:
        existing = await self.session.execute(
            select(Match).where(
                or_(
                    and_(Match.profile_a_id == profile_a_id, Match.profile_b_id == profile_b_id),
                    and_(Match.profile_a_id == profile_b_id, Match.profile_b_id == profile_a_id),
                )
            )
        )
        return existing.scalar_one_or_none() is None

    async def _create_match(
        self, seeker: Profile, provider: Profile, similarity: float
    ) -> Match:
        rationale = await self._generate_match_rationale(seeker, provider)

        match = Match(
            profile_a_id=seeker.id,
            profile_b_id=provider.id,
            similarity_score=similarity,
            match_rationale=rationale,
            status="pending",
        )
        self.session.add(match)
        return match

    async def _generate_match_rationale(self, seeker: Profile, provider: Profile) -> str:
        prompt = f"""Explain why these two profiles would be a good match for each other.

Seeker Profile:
{seeker.summary}
Structured Data: {seeker.structured_data}

Provider Profile:
{provider.summary}
Structured Data: {provider.structured_data}

Provide a brief, friendly explanation (2-3 sentences) of why they match well."""

        return await self.llm.chat([{"role": "user", "content": prompt}], "")

