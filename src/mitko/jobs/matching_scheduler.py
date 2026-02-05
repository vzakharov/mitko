"""Matching scheduler: queue-based single-match processing."""

import asyncio
import logging

from aiogram import Bot

from ..models import async_session_maker
from ..services.generation_orchestrator import GenerationOrchestrator
from ..services.matcher import MatcherService

logger = logging.getLogger(__name__)

# Global constant for retry interval when no matches found
MATCHING_RETRY_INTERVAL_SECONDS = 30 * 60  # 30 minutes

# Module-level task storage
_matching_task: asyncio.Task[None] | None = None


async def run_matching_loop(bot: Bot) -> None:
    """Find and enqueue one match, then exit. Retry if none found.

    This function:
    1. Finds the next match pair (earliest updated user + most similar opposite-role user)
    2. If found: creates generation, commits, and exits
    3. If not found: sleeps 30 minutes and retries

    After a match is enqueued, the generation processor handles rationale generation
    and notification. When complete, MatchGeneration restarts this loop for the next match.
    """
    logger.info("Starting matching loop")

    while True:
        async with async_session_maker() as session:
            if match := await MatcherService(session).find_next_match_pair():
                # Commit match to DB
                await session.commit()

                # Create generation (respects budget interval)
                await GenerationOrchestrator(session).create_generation(
                    match_id=match.id
                )
                await session.commit()

                logger.info(
                    "Enqueued match %s (users %s ↔ %s, similarity=%.2f) for generation",
                    match.id,
                    match.user_a_id,
                    match.user_b_id,
                    match.similarity_score,
                )

                return  # Exit - will be restarted after generation completes
            else:
                # No matches found - sleep and retry
                # TODO: Replace with nudge mechanism when profiles are updated
                logger.info(
                    "No matches found, sleeping %d seconds",
                    MATCHING_RETRY_INTERVAL_SECONDS,
                )
                await asyncio.sleep(MATCHING_RETRY_INTERVAL_SECONDS)


def start_matching_loop(bot: Bot) -> None:
    """Start the matching loop as a background task."""
    global _matching_task
    _matching_task = asyncio.create_task(run_matching_loop(bot))
    logger.info("Matching loop started")


def stop_matching_loop() -> None:
    """Stop the matching loop gracefully."""
    global _matching_task
    if _matching_task and not _matching_task.done():
        _matching_task.cancel()
        logger.info("Matching loop stopped")
