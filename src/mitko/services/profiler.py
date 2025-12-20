from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, Conversation
from ..llm import get_embedding_provider
from ..agents import ProfileData, SummaryAgent, get_model_name


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_profile(
        self, user: User, conversation: Conversation, profile_data: ProfileData
    ) -> User:
        is_seeker = profile_data.is_seeker
        is_provider = profile_data.is_provider
        summary = profile_data.summary

        if not summary or not summary.strip():
            summary = await self._generate_summary(conversation)

        embedding_provider = await get_embedding_provider()
        embedding = await embedding_provider.embed(summary)

        user.is_seeker = is_seeker
        user.is_provider = is_provider
        user.summary = summary
        user.embedding = embedding
        user.is_complete = True
        user.state = "active"

        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def _generate_summary(self, conversation: Conversation) -> str:
        summary_agent = SummaryAgent(get_model_name())
        return await summary_agent.generate_summary(conversation.messages)

