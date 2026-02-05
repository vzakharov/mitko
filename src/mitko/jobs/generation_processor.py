"""Generation processor for scheduled LLM response generation.

This module implements a sequential queue system for LLM generation:
- Generations are scheduled with a scheduled_for timestamp
- The processor awaits the earliest pending scheduled_for, generates a response, then repeats
- Only one generation happens at a time (sequential, not parallel)

This is the infrastructure layer that orchestrates the queue processing.
Actual business logic lives in services/ (ConversationGeneration, GenerationOrchestrator, etc.)
"""

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Generation, async_session_maker
from ..services.conversation_generation import ConversationGeneration
from ..services.generation_orchestrator import GenerationOrchestrator

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


async def _route_and_process(
    bot: Bot, generation: Generation, session: AsyncSession
) -> None:
    """Route to task-specific processor based on which FK is set."""
    if generation.conversation is not None:
        await ConversationGeneration(
            bot, session, generation, generation.conversation
        ).execute()
    else:
        raise ValueError(f"Generation {generation.id} has no associated task")


async def _processor_loop(bot: Bot) -> None:
    """Main processor loop - runs indefinitely, processing one generation at a time."""
    event = _get_nudge_event()

    while True:
        try:
            async with async_session_maker() as session:
                scheduler = GenerationOrchestrator(session)

                # Find next ripe generation
                generation = await scheduler.get_next_pending()

                if generation is not None:
                    # Mark as started
                    generation.status = "started"
                    generation.started_at = datetime.now(UTC)
                    await session.commit()

                    # Process the generation
                    try:
                        await _route_and_process(bot, generation, session)
                        await scheduler.mark_completed(generation)
                    except Exception as e:
                        logger.exception(
                            "Error processing generation %s: %s",
                            generation.id,
                            e,
                        )
                        await scheduler.mark_failed(generation)

                    # Immediately check for more work (no wait)
                    continue

                # No ripe generation - calculate wait time
                next_time = await scheduler.get_next_scheduled_time()

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
                # No pending generations - wait indefinitely for nudge
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
