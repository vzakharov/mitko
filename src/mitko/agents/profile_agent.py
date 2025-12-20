"""Profile extraction agent using PydanticAI"""

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName

from .models import ProfileData


class ProfileAgent:
    """Agent for extracting structured profile data from conversations"""

    SYSTEM_PROMPT = """You are Mitko, a friendly Telegram bot helping match IT professionals with job opportunities.

Your goal is to analyze conversations and extract structured profile information. You need to determine:

1. Their role(s) - IMPORTANT: Users can be BOTH seekers and providers simultaneously!
   - Job seeker: Looking for work (contract, full-time, part-time)
   - Provider: Hiring, contracting out work, or offering opportunities
   - Both: Some users actively seek work while also hiring others

2. Their skills, experience, preferences, and needs

3. For seekers: what kind of work they're looking for, their availability, rate expectations

4. For providers: what roles they're hiring for, requirements, budget

Pay special attention to users who mention both seeking work AND hiring/contracting - they should have both roles enabled!

When you have enough information, extract a structured profile with:
- is_seeker: true if they're looking for work
- is_provider: true if they're hiring or offering opportunities
- summary: A 2-3 sentence summary of who they are and what they're looking for
- structured_data: A dictionary containing:
  - skills: list of skills mentioned
  - experience_years: number of years experience (or null)
  - location: their location (or null)
  - rate_range: their rate expectations (or null)
  - hiring_for: list of roles they're hiring for (or null/empty if not a provider)
  - availability: their availability (full-time/part-time/contract/etc, or null)

IMPORTANT:
- At least one of is_seeker or is_provider must be true
- Both can be true if the user wants to both seek work AND hire/contract
- Listen carefully for clues that indicate both roles
"""

    def __init__(self, model_name: KnownModelName):
        """
        Initialize the profile extraction agent.

        Args:
            model_name: The LLM model to use (e.g., "openai:gpt-4o-mini", "anthropic:claude-3-5-sonnet-20241022")
        """
        self._agent = Agent(
            model_name,
            result_type=ProfileData,
            system_prompt=self.SYSTEM_PROMPT,
        )

    async def extract_profile(
        self, conversation_messages: list[dict[str, str]]
    ) -> ProfileData:
        """
        Extract structured profile data from a conversation.

        Args:
            conversation_messages: List of conversation messages with 'role' and 'content' keys

        Returns:
            ProfileData: Validated structured profile data

        Raises:
            ValueError: If profile data is invalid or incomplete
        """
        # Convert conversation to a user prompt for the agent
        conversation_text = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in conversation_messages
        )

        prompt = f"""Based on the following conversation, extract the user's profile information:

{conversation_text}

Extract and structure the profile data now."""

        result = await self._agent.run(prompt)
        return result.data
