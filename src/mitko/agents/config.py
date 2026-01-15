"""Configuration helpers for PydanticAI agents"""

from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel

from ..config import SETTINGS

OPENAI_MODEL = OpenAIChatModel("gpt-5-mini")
OPENAI_RESPONSES_MODEL = OpenAIResponsesModel("gpt-4.1")
ANTHROPIC_MODEL = AnthropicModel("claude-3-7-sonnet-latest")


def get_language_model():
    """
    Get the PydanticAI model name based on the configured LLM provider.

    Returns:
        KnownModelName: The model identifier for PydanticAI

    Raises:
        ValueError: If the provider is unknown
    """
    if SETTINGS.llm_provider == "openai":
        if SETTINGS.use_openai_responses_api:
            return OPENAI_RESPONSES_MODEL
        else:
            return OPENAI_MODEL
    elif SETTINGS.llm_provider == "anthropic":
        return ANTHROPIC_MODEL
    else:
        raise ValueError(f"Unsupported LLM provider: {SETTINGS.llm_provider}")


LANGUAGE_MODEL = get_language_model()
