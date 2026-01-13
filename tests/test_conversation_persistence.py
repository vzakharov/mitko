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
from src.mitko.types.messages import (
    AssistantMessage,
    ConversationResponse,
    ProfileData,
    UserMessage,
)


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
        conv = Conversation(telegram_id=123456789, messages=[])
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Simulate /start: initialize with empty messages (greeting in system prompt)
        conv.messages = []
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have empty message history
        assert len(conv.messages) == 0

    async def test_start_clears_existing_messages(
        self, test_session: AsyncSession
    ) -> None:
        """Test /start clears existing conversation history"""
        # Create conversation with existing messages
        conv = Conversation(
            telegram_id=123456789,
            messages=[
                AssistantMessage(
                    role="assistant",
                    content=ConversationResponse(
                        utterance="Old greeting", profile=None
                    ),
                ),
                UserMessage(role="user", content="User message"),
                AssistantMessage(
                    role="assistant",
                    content=ConversationResponse(
                        utterance="Bot response", profile=None
                    ),
                ),
            ],
        )
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify initial state
        assert len(conv.messages) == 3

        # Simulate /start: clear all messages (greeting in system prompt)
        conv.messages = []
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have empty message history
        assert len(conv.messages) == 0

    async def test_reset_clears_messages(
        self, test_session: AsyncSession
    ) -> None:
        """Test reset confirmation clears message history"""
        # Create conversation with existing messages
        conv = Conversation(
            telegram_id=123456789,
            messages=[
                AssistantMessage(
                    role="assistant",
                    content=ConversationResponse(
                        utterance="Greeting", profile=None
                    ),
                ),
                UserMessage(role="user", content="I want to reset"),
                AssistantMessage(
                    role="assistant",
                    content=ConversationResponse(
                        utterance="Are you sure?", profile=None
                    ),
                ),
            ],
        )
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Simulate reset confirmation: clear messages (greeting in system prompt)
        conv.messages = []
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have empty message history
        assert len(conv.messages) == 0

    async def test_regular_messages_append(
        self, test_session: AsyncSession
    ) -> None:
        """Test regular conversation messages append correctly"""
        # Create conversation with empty history (greeting in system prompt)
        conv = Conversation(telegram_id=123456789, messages=[])
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Append user message
        conv.messages.append(UserMessage(role="user", content="Hello bot"))
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have 1 message
        assert len(conv.messages) == 1

        # Append assistant response
        conv.messages.append(
            AssistantMessage(
                role="assistant",
                content=ConversationResponse(
                    utterance="Hello user", profile=None
                ),
            )
        )
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify: should have 2 messages in correct order
        assert len(conv.messages) == 2
        assert conv.messages[0].role == "user"
        assert conv.messages[0].content == "Hello bot"
        assert conv.messages[1].role == "assistant"
        assert conv.messages[1].content.utterance == "Hello user"

    async def test_persistence_across_sessions(
        self, test_engine: AsyncEngine
    ) -> None:
        """Verify messages persist when read from fresh session"""
        # Create session and conversation
        session_maker = async_sessionmaker(
            test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with session_maker() as session1:
            conv = Conversation(
                telegram_id=987654321,
                messages=[
                    AssistantMessage(
                        role="assistant",
                        content=ConversationResponse(
                            utterance="Greeting", profile=None
                        ),
                    ),
                    UserMessage(role="user", content="Test message"),
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
            msg0 = fresh_conv.messages[0]
            msg1 = fresh_conv.messages[1]
            assert isinstance(msg0, AssistantMessage)
            assert msg0.content.utterance == "Greeting"
            assert isinstance(msg1, UserMessage)
            assert msg1.content == "Test message"

    async def test_assistant_message_with_profile_data(
        self, test_session: AsyncSession
    ) -> None:
        """Test assistant message with profile data serializes/deserializes correctly"""
        # Create conversation with assistant message containing profile
        conv = Conversation(
            telegram_id=123456789,
            messages=[
                AssistantMessage(
                    role="assistant",
                    content=ConversationResponse(
                        utterance="Great! I've created your profile.",
                        profile=ProfileData(
                            is_seeker=True,
                            is_provider=False,
                            summary="Senior Python developer with 5 years experience",
                        ),
                    ),
                )
            ],
        )
        test_session.add(conv)
        await test_session.commit()
        await test_session.refresh(conv)

        # Verify profile data persisted
        assert len(conv.messages) == 1
        msg = conv.messages[0]
        assert msg.role == "assistant"
        assert msg.content.utterance == "Great! I've created your profile."
        assert msg.content.profile is not None
        assert msg.content.profile.is_seeker is True
        assert msg.content.profile.is_provider is False
        assert (
            msg.content.profile.summary
            == "Senior Python developer with 5 years experience"
        )
