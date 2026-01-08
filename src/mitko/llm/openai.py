
from openai import AsyncOpenAI

from ..config import settings


class OpenAIProvider:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.chat_model = "gpt-4o-mini"
        self.embedding_model = "text-embedding-3-small"

    async def chat(self, messages: list[dict[str, str]], system: str) -> str:
        formatted_messages = [{"role": "system", "content": system}] + messages
        response = await self.client.chat.completions.create(
            model=self.chat_model,
            messages=formatted_messages,
        )
        return response.choices[0].message.content or ""

    async def embed(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(
            model=self.embedding_model,
            input=text,
        )
        return response.data[0].embedding

