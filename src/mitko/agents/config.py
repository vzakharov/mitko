"""Configuration helpers for PydanticAI agents"""

from pydantic_ai.models import KnownModelName

from ..config import settings


def get_model_name() -> KnownModelName:
    """
    Get the PydanticAI model name based on the configured LLM provider.

    Returns:
        KnownModelName: The model identifier for PydanticAI

    Raises:
        ValueError: If the provider is unknown
    """
    if settings.llm_provider == "openai":
        return "openai:gpt-4o-mini"
    elif settings.llm_provider == "anthropic":
        return "anthropic:claude-3-5-sonnet-20241022"
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
