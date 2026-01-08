from typing import Literal, Protocol, TypedDict


class LLMMessage(TypedDict):
    """Type-safe message structure for LLM conversations"""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMProvider(Protocol):
    async def chat(self, messages: list[LLMMessage], system: str) -> str:
        ...

    async def embed(self, text: str) -> list[float]:
        ...

