from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, Conversation
from ..llm import LLMProvider, get_embedding_provider
from ..utils import validate_profile_roles


class ProfileService:
    def __init__(self, session: AsyncSession, llm: LLMProvider) -> None:
        self.session = session
        self.llm = llm

    async def create_profile(
        self, user: User, conversation: Conversation, profile_data: dict
    ) -> User:
        # Validate role fields
        validate_profile_roles(profile_data)

        is_seeker = profile_data.get("is_seeker", False)
        is_provider = profile_data.get("is_provider", False)
        summary = profile_data.get("summary", "")
        structured_data = profile_data.get("structured_data", {})

        if not summary:
            summary = await self._generate_summary(conversation)

        embedding_provider = await get_embedding_provider()
        embedding = await embedding_provider.embed(summary)

        # Update user directly (no separate Profile model)
        user.is_seeker = is_seeker
        user.is_provider = is_provider
        user.summary = summary
        user.structured_data = structured_data
        user.embedding = embedding
        user.is_complete = True
        user.state = "active"

        await self.session.commit()
        await self.session.refresh(user)
        return user

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

