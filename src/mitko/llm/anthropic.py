from anthropic import AsyncAnthropic

from ..config import settings
from .embeddings import get_embedding_provider


class AnthropicProvider:
    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.chat_model = "claude-3-5-sonnet-20241022"
        self._embedding_provider = None

    async def chat(self, messages: list[dict[str, str]], system: str) -> str:
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({"role": msg["role"], "content": msg["content"]})

        response = await self.client.messages.create(
            model=self.chat_model,
            max_tokens=4096,
            system=system,
            messages=formatted_messages,
        )
        return response.content[0].text

    async def embed(self, text: str) -> list[float]:
        if self._embedding_provider is None:
            self._embedding_provider = await get_embedding_provider()
        return await self._embedding_provider.embed(text)

