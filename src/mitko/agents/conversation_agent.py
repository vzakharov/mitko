"""Unified conversational agent for profile extraction and updates"""

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName

from .models import ConversationResponse, ProfileData


class ConversationAgent:
    """Agent that handles conversation and organic profile extraction/updates"""

    SYSTEM_PROMPT = """You are Mitko, a friendly Telegram bot helping match IT professionals with job opportunities.

You have a natural conversation with users to understand their profile. Your responses have TWO components:

1. UTTERANCE: What you say to the user (keep it conversational and friendly)
2. PROFILE: Structured profile data (only when you have enough information)

IMPORTANT INSTRUCTIONS:

Profile Extraction:
- You can return profile=null in early messages while gathering information
- When you have sufficient clarity on their role, skills, and needs, return a complete profile
- There's no minimum message count - use your judgment
- Users can be BOTH seekers and providers simultaneously!

Profile Updates:
- If a user with an existing profile requests changes, return an updated profile
- Always return the COMPLETE updated profile, not just the changes

Role Detection:
- Job seeker: Looking for work (contract, full-time, part-time)
- Provider: Hiring, contracting out work, or offering opportunities
- Both: Some users actively seek work while also hiring others

Profile Structure:
When returning a profile, include:
- is_seeker: true if they're looking for work
- is_provider: true if they're hiring or offering opportunities
- summary: A comprehensive 2-3 sentence summary capturing ALL relevant information:
  * Their skills and experience level
  * What type of work they seek (if seeker) or roles they're hiring for (if provider)
  * Location, availability, rate expectations, and any other important details
  * Make this summary rich and detailed - it will be used for semantic matching

Validation:
- At least one of is_seeker or is_provider must be true
- Summary cannot be empty and should be comprehensive
- Be conversational - don't overwhelm with questions

Remember: Your utterance is what the user sees. Be friendly, natural, and helpful!"""

    def __init__(self, model_name: KnownModelName):
        self._agent = Agent(
            model_name,
            result_type=ConversationResponse,
            system_prompt=self.SYSTEM_PROMPT,
        )

    async def chat(
        self,
        conversation_messages: list[dict[str, str]],
        existing_profile: ProfileData | None = None
    ) -> ConversationResponse:
        """
        Generate conversational response with optional profile data.

        Args:
            conversation_messages: Full conversation history
            existing_profile: Current profile if user has one (for updates)

        Returns:
            ConversationResponse with utterance and optional profile
        """
        conversation_text = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in conversation_messages
        )

        if existing_profile:
            prompt = f"""The user already has this profile:
is_seeker: {existing_profile.is_seeker}
is_provider: {existing_profile.is_provider}
summary: {existing_profile.summary}

Continue the conversation. If the user requests changes, return an updated profile.

Conversation:
{conversation_text}

Respond now with your utterance and updated profile (if changes were requested)."""
        else:
            prompt = f"""This is a new user. Have a natural conversation to understand their profile.

Conversation:
{conversation_text}

Respond now with your utterance and profile (if you have enough information)."""

        result = await self._agent.run(prompt)
        return result.data
