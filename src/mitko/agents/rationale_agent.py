"""Match rationale generation agent using PydanticAI"""

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName

from .models import MatchRationale


class RationaleAgent:
    """Agent for generating structured match rationales"""

    SYSTEM_PROMPT = """You are an expert IT matchmaker who explains why two professionals would work well together.

Your task is to analyze two IT professional profiles and explain why they're a good match.

Provide:
1. A brief, friendly explanation (2-3 sentences) of why they match well
2. A list of 2-4 key alignment points (specific skills, experience, or needs that align)
3. A confidence score (0.0 to 1.0) representing how strong the match is

Focus on:
- Complementary skills and needs
- Matching experience levels or requirements
- Location or availability alignment
- Technology stack overlap
- Role compatibility (seeker ↔ provider)

Be specific and highlight the most relevant connections.
"""

    def __init__(self, model_name: KnownModelName):
        """
        Initialize the rationale generation agent.

        Args:
            model_name: The LLM model to use (e.g., "openai:gpt-4o-mini", "anthropic:claude-3-5-sonnet-20241022")
        """
        self._agent = Agent(
            model_name,
            result_type=MatchRationale,
            system_prompt=self.SYSTEM_PROMPT,
        )

    async def generate_rationale(
        self,
        seeker_summary: str,
        seeker_data: dict,
        provider_summary: str,
        provider_data: dict,
    ) -> MatchRationale:
        """
        Generate a structured match rationale.

        Args:
            seeker_summary: Summary of the seeker's profile
            seeker_data: Structured data from the seeker's profile
            provider_summary: Summary of the provider's profile
            provider_data: Structured data from the provider's profile

        Returns:
            MatchRationale: Structured rationale with explanation, alignments, and confidence

        Raises:
            ValueError: If rationale generation fails or produces invalid output
        """
        prompt = f"""Analyze these two profiles and explain why they're a good match:

Seeker Profile:
Summary: {seeker_summary}
Structured Data: {seeker_data}

Provider Profile:
Summary: {provider_summary}
Structured Data: {provider_data}

Generate a structured match rationale with:
- explanation: A brief, friendly 2-3 sentence explanation
- key_alignments: A list of 2-4 specific points where they align
- confidence_score: A score from 0.0 to 1.0 (where 1.0 is a perfect match)"""

        result = await self._agent.run(prompt)
        return result.data
