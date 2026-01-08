from ..config import settings
from .anthropic import AnthropicProvider
from .base import LLMProvider
from .embeddings import get_embedding_provider as get_embedding_provider
from .openai import OpenAIProvider


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "openai":
        return OpenAIProvider()
    elif settings.llm_provider == "anthropic":
        return AnthropicProvider()
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

