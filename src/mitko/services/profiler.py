from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..llm import get_embedding
from ..models import Chat, User
from ..models.user import CURRENT_PROFILER_VERSION
from ..types.messages import ProfileData


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_or_update_profile(
        self, user: User, profile_data: ProfileData, is_update: bool = False
    ) -> User:
        """
        Create a new profile or update an existing one.

        After this call the user's state is "ready" (new) or "updated" (existing active
        profile changed). They must explicitly press the activation button to become
        matchable (state = "active").

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

        # Require explicit activation — user must press the keyboard button
        user.state = "updated" if is_update else "ready"
        user.profiler_version = CURRENT_PROFILER_VERSION
        user.profile_updated_at = datetime.now()

        await self.session.commit()
        await self.session.refresh(user)

        return user

    async def activate_profile(self, user: User) -> User:
        user.state = "active"
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def create_profile(
        self, user: User, chat: Chat, profile_data: ProfileData
    ) -> User:
        """Legacy method - redirects to create_or_update_profile"""
        return await self.create_or_update_profile(
            user, profile_data, is_update=False
        )

    async def reset_profile(self, user: User, chat: Chat | None) -> None:
        """
        Reset user profile and chat to blank state.

        Args:
            user: User to reset
            chat: Chat to clear (if exists)
        """
        # Reset user fields to defaults
        user.is_seeker = None
        user.is_provider = None
        user.matching_summary = None
        user.practical_context = None
        user.private_observations = None
        user.embedding = None
        user.state = "onboarding"
        user.profiler_version = None
        user.profile_updated_at = None

        # Clear chat history (keep the record)
        if chat:
            chat.message_history = []
            chat.user_prompt = None

        await self.session.commit()
