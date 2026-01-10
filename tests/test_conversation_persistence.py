"""Integration tests for conversation message persistence"""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import col

from src.mitko.i18n import L
from src.mitko.models.conversation import Conversation


@pytest.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create test database engine with in-memory SQLite"""
    # Use SQLite for testing (faster and doesn't require PostgreSQL)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create only the conversations table (avoid pgvector dependency)
    async with engine.begin() as conn:
        await conn.run_sync(Conversation.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create test session"""
    session_maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session


class TestConversationPersistence:
    """Test that conversation message changes persist to database"""

    async def test_start_creates_single_greeting(self, test_session: AsyncSession) -> None:
        """Test /start creates conversation with only greeting message"""
        # Create conversation
        conv = Conversation(telegram_id=123456789, messages=[])
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Simulate /start: replace messages with greeting
        conv.messages = [{"role": "assistant", "content": L.commands.start.GREETING}]
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have exactly 1 message
        assert len(conv.messages) == 1
        assert conv.messages[0]["role"] == "assistant"
        assert conv.messages[0]["content"] == L.commands.start.GREETING

    async def test_start_replaces_existing_messages(self, test_session: AsyncSession) -> None:
        """Test /start replaces existing conversation history"""
        # Create conversation with existing messages
        conv = Conversation(
            telegram_id=123456789,
            messages=[
                {"role": "assistant", "content": "Old greeting"},
                {"role": "user", "content": "User message"},
                {"role": "assistant", "content": "Bot response"},
            ],
        )
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify initial state
        assert len(conv.messages) == 3

        # Simulate /start: replace all messages with new greeting
        conv.messages = [{"role": "assistant", "content": L.commands.start.GREETING}]
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have exactly 1 message (not 4)
        assert len(conv.messages) == 1
        assert conv.messages[0]["role"] == "assistant"
        assert conv.messages[0]["content"] == L.commands.start.GREETING

    async def test_reset_replaces_messages(self, test_session: AsyncSession) -> None:
        """Test reset confirmation replaces messages with greeting"""
        # Create conversation with existing messages
        conv = Conversation(
            telegram_id=123456789,
            messages=[
                {"role": "assistant", "content": "Greeting"},
                {"role": "user", "content": "I want to reset"},
                {"role": "assistant", "content": "Are you sure?"},
            ],
        )
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Simulate reset confirmation: replace messages with greeting
        conv.messages = [{"role": "assistant", "content": L.commands.start.GREETING}]
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have exactly 1 message
        assert len(conv.messages) == 1
        assert conv.messages[0]["role"] == "assistant"
        assert conv.messages[0]["content"] == L.commands.start.GREETING

    async def test_regular_messages_append(self, test_session: AsyncSession) -> None:
        """Test regular conversation messages append correctly"""
        # Create conversation with greeting
        conv = Conversation(
            telegram_id=123456789,
            messages=[{"role": "assistant", "content": L.commands.start.GREETING}],
        )
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Append user message
        conv.messages.append({"role": "user", "content": "Hello bot"})
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have 2 messages
        assert len(conv.messages) == 2

        # Append assistant response
        conv.messages.append({"role": "assistant", "content": "Hello user"})
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have 3 messages in correct order
        assert len(conv.messages) == 3
        assert conv.messages[0]["role"] == "assistant"
        assert conv.messages[0]["content"] == L.commands.start.GREETING
        assert conv.messages[1]["role"] == "user"
        assert conv.messages[1]["content"] == "Hello bot"
        assert conv.messages[2]["role"] == "assistant"
        assert conv.messages[2]["content"] == "Hello user"

    async def test_persistence_across_sessions(self, test_engine: AsyncEngine) -> None:
        """Verify messages persist when read from fresh session"""
        # Create session and conversation
        session_maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        async with session_maker() as session1:
            conv = Conversation(
                telegram_id=987654321,
                messages=[
                    {"role": "assistant", "content": "Greeting"},
                    {"role": "user", "content": "Test message"},
                ],
            )
            session1.add(conv)
            await session1.commit()
            conv_id = conv.id

        # Create fresh session and query
        async with session_maker() as session2:
            result = await session2.execute(
                select(Conversation).where(col(Conversation.id) == conv_id)
            )
            fresh_conv = result.scalar_one()

            # Verify messages persisted
            assert len(fresh_conv.messages) == 2
            assert fresh_conv.messages[0]["content"] == "Greeting"
            assert fresh_conv.messages[1]["content"] == "Test message"
