"""MockedBot for testing — adapted from aiogram's own test suite.

Instead of hitting Telegram's API, MockedSession captures outgoing requests
in a deque and returns pre-staged responses.  Usage:

    bot = MockedBot()
    msg.as_(bot)                              # inject into TelegramObject
    bot.add_result_for(SendMessage, ok=True)  # stage a response
    await handler(msg)                        # run the handler
    req = bot.get_request()                   # inspect what was sent
    assert isinstance(req, SendMessage)
    assert req.text == "expected"

Source: https://github.com/aiogram/aiogram/blob/dev-3.x/tests/mocked_bot.py
"""

from collections import deque
from collections.abc import AsyncGenerator

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.methods.base import Response, TelegramType
from aiogram.types import ResponseParameters, User


class MockedSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.responses: deque[Response[object]] = deque()
        self.requests: deque[TelegramMethod[object]] = deque()
        self.closed = True

    def add_result(self, response: Response[object]) -> None:
        self.responses.append(response)

    def get_request(self) -> TelegramMethod[object]:
        return self.requests.pop()

    async def close(self) -> None:
        self.closed = True

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        self.closed = False
        self.requests.append(method)  # type: ignore[arg-type]
        response = self.responses.pop()
        self.check_response(
            bot=bot,
            method=method,
            status_code=response.error_code or 200,
            content=response.model_dump_json(),
        )
        return response.result  # type: ignore[return-value]

    async def stream_content(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:  # pragma: no cover
        yield b""


class MockedBot(Bot):
    session: MockedSession  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__("42:TEST", session=MockedSession())
        self._me = User(
            id=self.id,
            is_bot=True,
            first_name="TestBot",
            username="test_bot",
        )

    def add_result_for(
        self,
        method: type[TelegramMethod[TelegramType]],
        ok: bool,
        result: TelegramType | None = None,
        description: str | None = None,
        error_code: int = 200,
    ) -> None:
        response = Response[method.__returning__](  # type: ignore[name-defined]
            ok=ok,
            result=result,
            description=description,
            error_code=error_code,
            parameters=ResponseParameters(),
        )
        self.session.add_result(response)

    def get_request(self) -> TelegramMethod[object]:
        return self.session.get_request()
