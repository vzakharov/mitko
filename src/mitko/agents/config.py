"""Configuration helpers for PydanticAI agents"""

from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel

from ..config import SETTINGS

# Lazy-initialized model instances (initialized only when accessed)
_openai_model = None
_openai_responses_model = None
_anthropic_model = None


def _get_openai_model() -> OpenAIChatModel:
    """Get or create OpenAI chat model."""
    global _openai_model
    if _openai_model is None:
        _openai_model = OpenAIChatModel("gpt-5-mini")
    return _openai_model


def _get_openai_responses_model() -> OpenAIResponsesModel:
    """Get or create OpenAI responses model."""
    global _openai_responses_model
    if _openai_responses_model is None:
        _openai_responses_model = OpenAIResponsesModel("gpt-4.1")
    return _openai_responses_model


def _get_anthropic_model() -> AnthropicModel:
    """Get or create Anthropic model."""
    global _anthropic_model
    if _anthropic_model is None:
        _anthropic_model = AnthropicModel("claude-3-7-sonnet-latest")
    return _anthropic_model


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
            return _get_openai_responses_model()
        else:
            return _get_openai_model()
    elif SETTINGS.llm_provider == "anthropic":
        return _get_anthropic_model()
    else:
        raise ValueError(f"Unsupported LLM provider: {SETTINGS.llm_provider}")


LANGUAGE_MODEL = get_language_model()
