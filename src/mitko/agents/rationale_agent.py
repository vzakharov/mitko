"""Match rationale generation agent using PydanticAI"""

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName

from .models import MatchRationale
from ..i18n import L


class RationaleAgent:
    """Agent for generating structured match rationales"""

    SYSTEM_PROMPT_BASE = """You are an expert IT matchmaker who explains why two professionals would work well together.

PERSONALITY: {personality_guidelines}

Your task is to analyze two IT professional profiles and explain why they're a good match.

Provide:
1. A brief, friendly explanation (2-3 sentences) of why they match well - be casual and enthusiastic!
2. A list of 2-4 key alignment points (specific skills, experience, or needs that align)
3. A confidence score (0.0 to 1.0) representing how strong the match is

Focus on:
- Complementary skills and needs
- Matching experience levels or requirements
- Location or availability alignment
- Technology stack overlap
- Role compatibility (seeker ↔ provider)

LANGUAGE REQUIREMENT:
- You MUST provide your explanation and key_alignments in {language_name}
- Be specific and highlight the most relevant connections
- Keep the tone casual, friendly, and slightly enthusiastic

Here are example explanations in {language_name}:
{examples}
"""

    def __init__(self, model_name: KnownModelName):
        """
        Initialize the rationale generation agent.

        Args:
            model_name: The LLM model to use (e.g., "openai:gpt-4o-mini", "anthropic:claude-3-5-sonnet-20241022")
        """
        language_name = "English" if L.language == "en" else "Russian"

        # Get example rationales from locale
        examples = "\n".join(f"- {ex}" for ex in L.agent_examples.rationale.EXAMPLES)

        # Format system prompt with language context and personality
        system_prompt = self.SYSTEM_PROMPT_BASE.format(
            language_name=language_name,
            personality_guidelines=L.agent_personality.TONE_GUIDELINES,
            examples=examples,
        )

        self._agent = Agent(
            model_name,
            result_type=MatchRationale,
            system_prompt=system_prompt,
        )

    async def generate_rationale(
        self,
        seeker_summary: str,
        provider_summary: str,
    ) -> MatchRationale:
        """
        Generate a structured match rationale.

        Args:
            seeker_summary: Summary of the seeker's profile
            provider_summary: Summary of the provider's profile

        Returns:
            MatchRationale: Structured rationale with explanation, alignments, and confidence

        Raises:
            ValueError: If rationale generation fails or produces invalid output
        """
        prompt = f"""Analyze these two profiles and explain why they're a good match:

Seeker Profile:
{seeker_summary}

Provider Profile:
{provider_summary}

Generate a structured match rationale with:
- explanation: A brief, friendly 2-3 sentence explanation
- key_alignments: A list of 2-4 specific points where they align
- confidence_score: A score from 0.0 to 1.0 (where 1.0 is a perfect match)"""

        result = await self._agent.run(prompt)
        return result.data
