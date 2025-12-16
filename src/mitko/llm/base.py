from typing import Protocol


class LLMProvider(Protocol):
    async def chat(self, messages: list[dict[str, str]], system: str) -> str:
        ...

    async def embed(self, text: str) -> list[float]:
        ...

