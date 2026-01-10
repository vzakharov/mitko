"""Configuration helpers for PydanticAI agents"""

from pydantic_ai.models import KnownModelName

from ..config import settings

OPENA_MODEL_NAME = "openai:gpt-5-mini"
ANTHROPIC_MODEL_NAME = "anthropic:claude-3-7-sonnet-latest"


def get_model_name() -> KnownModelName:
    """
    Get the PydanticAI model name based on the configured LLM provider.

    Returns:
        KnownModelName: The model identifier for PydanticAI

    Raises:
        ValueError: If the provider is unknown
    """
    if settings.llm_provider == "openai":
        return OPENA_MODEL_NAME
    elif settings.llm_provider == "anthropic":
        return ANTHROPIC_MODEL_NAME
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
