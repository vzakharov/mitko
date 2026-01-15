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
async def test_session(
    test_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """Create test session"""
    session_maker = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        yield session


class TestConversationPersistence:
    """Test that conversation message changes persist to database"""

    async def test_start_creates_empty_conversation(
        self, test_session: AsyncSession
    ) -> None:
        """Test /start creates conversation with empty message history"""
        # Create conversation
        conv = Conversation(telegram_id=123456789, message_history=[])
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Simulate /start: initialize with empty messages (greeting in system prompt)
        conv.message_history = []
        conv.user_prompt = None
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have empty message history and no pending prompt
        assert conv.message_history == []
        assert conv.user_prompt is None

    async def test_start_clears_existing_messages(
        self, test_session: AsyncSession
    ) -> None:
        """Test /start clears existing conversation history"""
        # Create conversation with existing messages and pending prompt
        conv = Conversation(
            telegram_id=123456789,
            message_history=[{"role": "assistant", "content": "Old greeting"}],
            user_prompt="pending message",
        )
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify initial state
        assert conv.message_history != []
        assert conv.user_prompt == "pending message"

        # Simulate /start: clear all messages (greeting in system prompt)
        conv.message_history = []
        conv.user_prompt = None
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have empty message history and no pending prompt
        assert conv.message_history == []
        assert conv.user_prompt is None

    async def test_reset_clears_messages(
        self, test_session: AsyncSession
    ) -> None:
        """Test reset confirmation clears message history"""
        # Create conversation with existing messages
        conv = Conversation(
            telegram_id=123456789,
            message_history=[{"role": "assistant", "content": "Greeting"}],
        )
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Simulate reset confirmation: clear messages (greeting in system prompt)
        conv.message_history = []
        conv.user_prompt = None
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have empty message history
        assert conv.message_history == []
        assert conv.user_prompt is None

    async def test_user_prompt_field(self, test_session: AsyncSession) -> None:
        """Test user_prompt field for pending messages"""
        # Create conversation with empty history
        conv = Conversation(telegram_id=123456789, message_history=[])
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Set user prompt
        conv.user_prompt = "Hello bot"
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: user_prompt is set
        assert conv.user_prompt == "Hello bot"

        # Simulate multiple rapid messages (append with newline)
        conv.user_prompt += "\n\nAnother message"
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: user_prompt contains both messages
        assert conv.user_prompt == "Hello bot\n\nAnother message"

        # Simulate generation consuming the prompt
        conv.user_prompt = None
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: user_prompt is cleared
        assert conv.user_prompt is None

    async def test_persistence_across_sessions(
        self, test_engine: AsyncEngine
    ) -> None:
        """Verify message history and user_prompt persist when read from fresh session"""
        # Create session and conversation
        session_maker = async_sessionmaker(
            test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with session_maker() as session1:
            conv = Conversation(
                telegram_id=987654321,
                message_history=[{"role": "assistant", "content": "test"}],
                user_prompt="pending message",
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

            # Verify fields persisted
            assert fresh_conv.message_history == [
                {"role": "assistant", "content": "test"}
            ]
            assert fresh_conv.user_prompt == "pending message"

    async def test_message_history_json_storage(
        self, test_session: AsyncSession
    ) -> None:
        """Test message_history_json field stores PydanticAI format"""
        # Create conversation with serialized message history
        conv = Conversation(
            telegram_id=123456789,
            message_history=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
        )
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify JSON storage persisted
        assert conv.message_history != []
        assert "Hello" in conv.message_history
        assert "Hi there!" in conv.message_history
