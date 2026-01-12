"""Generation processor for scheduled LLM response generation.

This module implements a sequential queue system for LLM generation:
- User messages are stored with a scheduled_for timestamp
- The processor awaits the earliest scheduled_for, generates a response, then repeats
- Only one generation happens at a time (sequential, not parallel)
"""

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime

from aiogram import Bot
from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..agents import ConversationAgent, ProfileData, get_model_name
from ..i18n import L
from ..models import Conversation, User, async_session_maker
from ..services.profiler import ProfileService
from ..types import AssistantMessage

logger = logging.getLogger(__name__)

# Module-level state
_nudge_event: asyncio.Event | None = None
_processor_task: asyncio.Task[None] | None = None


def _get_nudge_event() -> asyncio.Event:
    """Get or create the nudge event (lazy initialization)."""
    global _nudge_event
    if _nudge_event is None:
        _nudge_event = asyncio.Event()
    return _nudge_event


def nudge_processor() -> None:
    """Signal the processor that new work may be available."""
    event = _get_nudge_event()
    event.set()


async def _find_next_ripe_conversation(
    session: AsyncSession,
) -> Conversation | None:
    """Find the conversation with earliest scheduled_for <= now."""
    now = datetime.now(UTC)
    result = await session.execute(
        select(Conversation)
        .where(col(Conversation.scheduled_for) <= now)
        .order_by(col(Conversation.scheduled_for).asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_next_scheduled_time(session: AsyncSession) -> datetime | None:
    """Get the earliest scheduled_for time (for wait calculation)."""
    result = await session.execute(
        select(sql_func.min(Conversation.scheduled_for)).where(
            col(Conversation.scheduled_for).is_not(None)
        )
    )
    return result.scalar_one_or_none()


def _format_profile_card(profile: ProfileData) -> str:
    """Format profile as a user-visible card."""
    card_parts = [L.profile.CARD_HEADER + "\n"]

    # Role
    roles = list[str]()
    if profile.is_seeker:
        roles.append(L.profile.ROLE_SEEKER)
    if profile.is_provider:
        roles.append(L.profile.ROLE_PROVIDER)
    card_parts.append(
        f"{L.profile.ROLE_LABEL}: {L.profile.ROLE_SEPARATOR.join(roles)}"
    )

    # Summary
    card_parts.append(f"\n\n{profile.summary}")

    return "".join(card_parts)


async def _process_conversation(
    bot: Bot, conv: Conversation, session: AsyncSession
) -> None:
    """Process a single conversation: generate response and send it."""
    # Get user for profile operations
    result = await session.execute(
        select(User).where(col(User.telegram_id) == conv.telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        logger.error(
            "User %d not found for conversation %s", conv.telegram_id, conv.id
        )
        return

    # Run conversation agent
    conversation_agent = ConversationAgent(get_model_name())
    response = await conversation_agent.run(conv.messages)

    # Handle profile creation/update
    if response.profile:
        profiler = ProfileService(session)
        is_update = user.is_complete
        await profiler.create_or_update_profile(
            user, response.profile, is_update=is_update
        )

        # Send response with profile card
        profile_card = _format_profile_card(response.profile)
        await bot.send_message(
            conv.telegram_id, f"{response.utterance}\n\n{profile_card}"
        )
    else:
        await bot.send_message(conv.telegram_id, response.utterance)

    # Store assistant response
    conv.messages.append(AssistantMessage.create(response))
    await session.commit()

    logger.info(
        "Processed conversation for user %d: %d total messages",
        conv.telegram_id,
        len(conv.messages),
    )


async def _processor_loop(bot: Bot) -> None:
    """Main processor loop - runs indefinitely, processing one conversation at a time."""
    event = _get_nudge_event()

    while True:
        try:
            async with async_session_maker() as session:
                # Find next ripe conversation
                conv = await _find_next_ripe_conversation(session)

                if conv is not None:
                    # Mark as processing (clear scheduled_for)
                    conv.scheduled_for = None
                    await session.commit()

                    # Process the conversation
                    try:
                        await _process_conversation(bot, conv, session)
                    except Exception as e:
                        logger.exception(
                            "Error processing conversation %s for user %d: %s",
                            conv.id,
                            conv.telegram_id,
                            e,
                        )
                        # Continue to next iteration - don't let one error stop the processor

                    # Immediately check for more work (no wait)
                    continue

                # No ripe conversation - calculate wait time
                next_time = await _get_next_scheduled_time(session)

            # Wait logic (outside session context)
            if next_time is not None:
                now = datetime.now(UTC)
                wait_seconds = (next_time - now).total_seconds()
                if wait_seconds > 0:
                    event.clear()
                    with suppress(TimeoutError):
                        await asyncio.wait_for(
                            event.wait(), timeout=wait_seconds
                        )
            else:
                # No scheduled conversations - wait indefinitely for nudge
                event.clear()
                await event.wait()

        except Exception as e:
            logger.exception("Unexpected error in processor loop: %s", e)
            # Brief pause before retrying to avoid tight error loops
            await asyncio.sleep(1.0)


def start_generation_processor(bot: Bot) -> None:
    """Start the generation processor as a background task."""
    global _processor_task
    if _processor_task is not None:
        logger.warning("Generation processor already running")
        return

    _processor_task = asyncio.create_task(_processor_loop(bot))
    logger.info("Started generation processor")


async def stop_generation_processor() -> None:
    """Stop the generation processor gracefully."""
    global _processor_task, _nudge_event

    if _processor_task is not None:
        _processor_task.cancel()
        with suppress(asyncio.CancelledError):
            await _processor_task
        _processor_task = None
        logger.info("Stopped generation processor")

    _nudge_event = None
