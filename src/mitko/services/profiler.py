from sqlalchemy.ext.asyncio import AsyncSession

from ..llm import get_embedding
from ..models import Conversation, User
from ..types.messages import ProfileData


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_or_update_profile(
        self, user: User, profile_data: ProfileData, is_update: bool = False
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
            user.embedding = await get_embedding(profile_data.summary)

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

    async def reset_profile(
        self, user: User, conversation: Conversation | None
    ) -> None:
        """
        Reset user profile and conversation to blank state.

        Args:
            user: User to reset
            conversation: Conversation to clear (if exists)
        """
        # Reset user fields to defaults
        user.is_seeker = None
        user.is_provider = None
        user.summary = None
        user.embedding = None
        user.is_complete = False
        user.state = "onboarding"

        # Clear conversation history (keep the record)
        if conversation:
            conversation.message_history_json = b"[]"
            conversation.user_prompt = None

        await self.session.commit()
