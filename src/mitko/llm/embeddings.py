from typing import TYPE_CHECKING

from ..config import settings

if TYPE_CHECKING:
    from .base import LLMProvider


_embedding_provider: "LLMProvider | None" = None


async def get_embedding_provider() -> "LLMProvider":
    global _embedding_provider
    if _embedding_provider is None:
        if settings.llm_provider == "openai":
            from .openai import OpenAIProvider
            _embedding_provider = OpenAIProvider()
        else:
            from .openai import OpenAIProvider
            _embedding_provider = OpenAIProvider()
    return _embedding_provider

