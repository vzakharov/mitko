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
        # Track if matching_summary changed (triggers re-embedding)
        matching_summary_changed = (
            is_update and user.matching_summary != profile_data.matching_summary
        )

        # Update all profile fields
        user.is_seeker = profile_data.is_seeker
        user.is_provider = profile_data.is_provider
        user.matching_summary = profile_data.matching_summary
        user.practical_context = profile_data.practical_context
        user.private_observations = profile_data.private_observations

        # Generate embedding ONLY from matching_summary (Part 1)
        if not is_update or matching_summary_changed:
            user.embedding = await get_embedding(profile_data.matching_summary)

        # Mark profile as complete
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
        user.matching_summary = None
        user.practical_context = None
        user.private_observations = None
        user.embedding = None
        user.is_complete = False
        user.state = "onboarding"

        # Clear conversation history (keep the record)
        if conversation:
            conversation.message_history = []
            conversation.user_prompt = None

        await self.session.commit()
