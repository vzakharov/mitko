"""Summary generation agent using PydanticAI"""

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName

from .models import SummaryResult


class SummaryAgent:
    """Agent for generating concise profile summaries from conversations"""

    SYSTEM_PROMPT = """You are an expert at creating concise, informative summaries of IT professionals.

Your task is to generate a 2-3 sentence summary that captures:
- Who the person is (their role, experience level)
- What they're looking for in the IT job market
- Key skills or requirements

The summary should be:
- Professional but friendly in tone
- Focused on the most important information
- Easy to read and understand quickly
- Between 2-3 sentences (around 40-100 words)
"""

    def __init__(self, model_name: KnownModelName):
        """
        Initialize the summary generation agent.

        Args:
            model_name: The LLM model to use (e.g., "openai:gpt-4o-mini", "anthropic:claude-3-5-sonnet-20241022")
        """
        self._agent = Agent(
            model_name,
            result_type=SummaryResult,
            system_prompt=self.SYSTEM_PROMPT,
        )

    async def generate_summary(
        self, conversation_messages: list[dict[str, str]]
    ) -> str:
        """
        Generate a concise summary from a conversation.

        Args:
            conversation_messages: List of conversation messages with 'role' and 'content' keys

        Returns:
            str: A concise 2-3 sentence summary

        Raises:
            ValueError: If summary generation fails or produces invalid output
        """
        conversation_text = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in conversation_messages
        )

        prompt = f"""Based on the following conversation, generate a concise 2-3 sentence summary
that captures who this person is and what they're looking for in the IT job market.

Conversation:
{conversation_text}

Generate the summary now."""

        result = await self._agent.run(prompt)
        return result.data.summary
