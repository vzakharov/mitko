from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, TextBlock

from ..config import settings
from .base import LLMMessage
from .embeddings import get_embedding_provider


class AnthropicProvider:
    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.chat_model = "claude-3-5-sonnet-20241022"
        self._embedding_provider = None

    async def chat(self, messages: list[LLMMessage], system: str) -> str:
        # Convert our LLMMessage format to Anthropic's MessageParam format
        # Anthropic SDK expects role to be 'user' or 'assistant' (no 'system' in messages)
        formatted_messages: list[MessageParam] = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                # Convert system messages to user messages with clarifying prefix
                formatted_messages.append(
                    {"role": "user", "content": f"[System message]: {content}"}
                )
            elif role in ("user", "assistant"):
                # Type-safe: role is guaranteed to be 'user' or 'assistant' here
                formatted_messages.append({"role": role, "content": content})

        response = await self.client.messages.create(
            model=self.chat_model,
            max_tokens=4096,
            system=system,
            messages=formatted_messages,
        )

        # Type narrow the content block to TextBlock
        content_block = response.content[0]
        if isinstance(content_block, TextBlock):
            return content_block.text
        else:
            raise ValueError(f"Unexpected content type: {type(content_block).__name__}")

    async def embed(self, text: str) -> list[float]:
        if self._embedding_provider is None:
            self._embedding_provider = await get_embedding_provider()
        return await self._embedding_provider.embed(text)
