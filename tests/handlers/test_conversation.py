"""Test conversation message handler.

Key behaviors:
- Single message creates a generation with proper scheduling
- Multiple rapid messages append to user_prompt and update existing generation
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from aiogram.methods import SendMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from mitko.bot.handlers import handle_message
from mitko.db import get_or_create_chat, get_or_create_user
from mitko.models import Generation

from .helpers import make_bot, make_message, patch_get_db


async def test_single_message_creates_generation(db_session: AsyncSession):
    """First message creates a generation and sends status message."""
    bot = make_bot()
    msg = make_message(bot, text="I'm looking for a job", user_id=6001)

    # Mock budget calculation methods to avoid complex interval logic
    with (
        patch(
            "mitko.services.generation_orchestrator.GenerationOrchestrator._calculate_budget_interval",
            new_callable=AsyncMock,
            return_value=timedelta(seconds=0),
        ),
        patch(
            "mitko.services.generation_orchestrator.GenerationOrchestrator._get_max_scheduled_time",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        async with patch_get_db(db_session):
            await handle_message(msg)

    # Check that a generation was created
    result = await db_session.execute(
        select(Generation).where(col(Generation.status) == "pending")
    )
    generation = result.scalar_one_or_none()
    assert generation is not None

    # Check that user_prompt was stored
    chat = await get_or_create_chat(db_session, 6001)
    assert chat.user_prompt == "I'm looking for a job"

    # Check that status message was sent
    req = bot.get_request()
    assert isinstance(req, SendMessage)
    assert req.chat_id == 6001


async def test_multiple_rapid_messages_append_to_user_prompt(
    db_session: AsyncSession,
):
    """Rapid successive messages append to user_prompt and reuse pending generation."""
    # Create user and chat with an existing pending generation
    await get_or_create_user(db_session, 6002)
    chat = await get_or_create_chat(db_session, 6002)
    chat.user_prompt = "First message"

    # Create a pending generation
    generation = Generation(
        chat_id=chat.id,
        scheduled_for=datetime.now(UTC),
        status="pending",
    )
    db_session.add(generation)
    await db_session.commit()

    bot = make_bot()
    msg = make_message(bot, text="Second message", user_id=6002)

    with patch(
        "mitko.bot.handlers.GenerationOrchestrator.create_generation",
        new_callable=AsyncMock,
    ) as mock_create:
        async with patch_get_db(db_session):
            await handle_message(msg)

        # Should NOT create a new generation
        mock_create.assert_not_called()

    # Check that user_prompt was appended
    await db_session.refresh(chat)
    assert chat.user_prompt == "First message\n\nSecond message"

    # Check that NO new generation was created (still only 1)
    result = await db_session.execute(
        select(Generation).where(col(Generation.chat_id) == chat.id)
    )
    generations = result.scalars().all()
    assert len(generations) == 1
