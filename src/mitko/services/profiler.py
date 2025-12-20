from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, Conversation
from ..llm import get_embedding_provider
from ..agents import ProfileData


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_or_update_profile(
        self,
        user: User,
        profile_data: ProfileData,
        is_update: bool = False
    ) -> User:
        """
        Create a new profile or update an existing one.

        Args:
            user: User to update
            profile_data: New or updated profile data
            is_update: True if updating existing profile, False for new

        Returns:
            Updated user
        """
        # Check if summary changed (triggers re-embedding)
        summary_changed = is_update and user.summary != profile_data.summary

        # Update user fields
        user.is_seeker = profile_data.is_seeker
        user.is_provider = profile_data.is_provider
        user.summary = profile_data.summary

        # Re-generate embedding if summary changed or new profile
        if not is_update or summary_changed:
            embedding_provider = await get_embedding_provider()
            user.embedding = await embedding_provider.embed(profile_data.summary)

        # Mark as complete and active
        user.is_complete = True
        user.state = "active"

        await self.session.commit()
        await self.session.refresh(user)

        return user

    async def create_profile(
        self, user: User, conversation: Conversation, profile_data: ProfileData
    ) -> User:
        """Legacy method - redirects to create_or_update_profile"""
        return await self.create_or_update_profile(
            user, profile_data, is_update=False
        )

