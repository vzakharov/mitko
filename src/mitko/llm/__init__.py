from .base import LLMProvider
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider
from .embeddings import get_embedding_provider

from ..config import settings


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "openai":
        return OpenAIProvider()
    elif settings.llm_provider == "anthropic":
        return AnthropicProvider()
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

