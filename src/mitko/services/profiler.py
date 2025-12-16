from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import User, Conversation, Profile
from ..llm import LLMProvider, get_embedding_provider


class ProfileService:
    def __init__(self, session: AsyncSession, llm: LLMProvider) -> None:
        self.session = session
        self.llm = llm

    async def create_profile(
        self, user: User, conversation: Conversation, profile_data: dict
    ) -> Profile:
        role = profile_data.get("role", "seeker")
        summary = profile_data.get("summary", "")
        structured_data = profile_data.get("structured_data", {})

        if not summary:
            summary = await self._generate_summary(conversation)

        embedding_provider = await get_embedding_provider()
        embedding = await embedding_provider.embed(summary)

        existing_profile = await self.session.execute(
            select(Profile).where(Profile.telegram_id == user.telegram_id)
        )
        profile = existing_profile.scalar_one_or_none()

        if profile:
            profile.role = role
            profile.summary = summary
            profile.structured_data = structured_data
            profile.embedding = embedding
            profile.is_complete = True
        else:
            profile = Profile(
                telegram_id=user.telegram_id,
                role=role,
                summary=summary,
                structured_data=structured_data,
                embedding=embedding,
                is_complete=True,
            )
            self.session.add(profile)

        user.role = role
        user.state = "active"

        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def _generate_summary(self, conversation: Conversation) -> str:
        prompt = """Based on the following conversation, generate a concise 2-3 sentence summary 
        that captures who this person is and what they're looking for in the IT job market.
        
        Conversation:
        {conversation_text}
        
        Summary:""".format(
            conversation_text="\n".join(
                f"{msg['role']}: {msg['content']}" for msg in conversation.messages
            )
        )

        return await self.llm.chat([{"role": "user", "content": prompt}], "")

