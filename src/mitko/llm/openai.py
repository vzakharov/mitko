from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from ..config import settings
from .base import LLMMessage


class OpenAIProvider:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.chat_model = "gpt-4o-mini"
        self.embedding_model = "text-embedding-3-small"

    async def chat(self, messages: list[LLMMessage], system: str) -> str:
        # Convert our LLMMessage format to OpenAI's typed message params
        formatted_messages: list[ChatCompletionMessageParam] = []

        # Add system message first
        system_msg: ChatCompletionSystemMessageParam = {"role": "system", "content": system}
        formatted_messages.append(system_msg)

        # Add conversation messages with proper types
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                typed_msg: ChatCompletionSystemMessageParam = {"role": "system", "content": content}
                formatted_messages.append(typed_msg)
            elif role == "user":
                typed_msg_user: ChatCompletionUserMessageParam = {
                    "role": "user",
                    "content": content,
                }
                formatted_messages.append(typed_msg_user)
            elif role == "assistant":
                typed_msg_asst: ChatCompletionAssistantMessageParam = {
                    "role": "assistant",
                    "content": content,
                }
                formatted_messages.append(typed_msg_asst)

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
