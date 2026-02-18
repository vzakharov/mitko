"""Embeddings generation using OpenAI (regardless of chat provider)"""

from openai import AsyncOpenAI

from ..settings_instance import SETTINGS

_client: AsyncOpenAI | None = None


async def get_embedding(text: str) -> list[float]:
    """
    Generate embedding for text using OpenAI.

    Note: Always uses OpenAI embeddings regardless of LLM_PROVIDER setting.
    This is intentional - embeddings require consistency for matching.
    """
    global _client
    if _client is None:
        if not SETTINGS.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for embeddings")
        _client = AsyncOpenAI(api_key=SETTINGS.openai_api_key)

    response = await _client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding
