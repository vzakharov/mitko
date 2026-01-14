"""Match rationale generation agent using PydanticAI"""

from textwrap import dedent

from pydantic_ai import Agent, AgentRunResult

from ..i18n import L
from .config import MODEL_NAME
from .models import MatchRationale


class RationaleAgent(Agent[None, MatchRationale]):
    """Agent for generating structured match rationales"""

    SYSTEM_PROMPT_BASE = dedent(
        """\
        You are an expert IT matchmaker who explains why two professionals would work well
        together.

        Your task is to analyze two IT professional profiles and explain why they're a good match.

        Provide:
        1. A brief, friendly explanation (2-3 sentences) of why they match well - be casual!
        2. A list of 2-4 key alignment points (skills, experience, or needs that align)
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
    )

    def __init__(self):
        """Initialize the rationale generation agent."""
        language_name = "English" if L.language == "en" else "Russian"

        # Get example rationales from locale
        examples = "\n".join(
            f"- {ex}" for ex in L.agent_examples.rationale.EXAMPLES
        )

        # Format instructions with language context
        instructions = self.SYSTEM_PROMPT_BASE.format(
            language_name=language_name,
            examples=examples,
        )

        super().__init__(
            MODEL_NAME,
            output_type=MatchRationale,
            instructions=instructions,
        )

    async def generate_rationale(
        self,
        seeker_summary: str,
        provider_summary: str,
    ) -> AgentRunResult[MatchRationale]:
        """
        Generate a structured match rationale.

        Args:
            seeker_summary: Summary of the seeker's profile
            provider_summary: Summary of the provider's profile

        Returns:
            AgentRunResult[MatchRationale]: Full result with structured rationale

        Raises:
            ValueError: If rationale generation fails or produces invalid output
        """
        prompt = dedent(
            f"""Analyze these two profiles and explain why they're a good match:

            Seeker Profile:
            {seeker_summary}

            Provider Profile:
            {provider_summary}

            Generate a structured match rationale with:
            - explanation: A brief, friendly 2-3 sentence explanation
            - key_alignments: A list of 2-4 specific points where they align
            - confidence_score: A score from 0.0 to 1.0 (where 1.0 is a perfect match)"""
        )

        return await self.run(prompt)


RATIONALE_AGENT = RationaleAgent()
