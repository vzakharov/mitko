"""Matching scheduler: queue-based single-match processing."""

import asyncio
import logging

from aiogram import Bot

from ..models import async_session_maker
from ..services.generation_orchestrator import GenerationOrchestrator
from ..services.match_result import AllUsersMatched, MatchFound, RoundExhausted
from ..services.matcher import MatcherService

logger = logging.getLogger(__name__)

# Global constant for retry interval when no matches found
MATCHING_RETRY_INTERVAL_SECONDS = 30 * 60  # 30 minutes

# Module-level task storage
_matching_task: asyncio.Task[None] | None = None


async def run_matching_loop() -> None:
    """Find and enqueue one match, then exit. Handle round progression.

    This function:
    1. Finds the next match pair (round-robin algorithm)
    2. Handles round advancement when current round exhausted
    3. Creates generation for real matches (not participation records)
    4. Sleeps only when no complete users exist at all
    """
    logger.info("Starting matching loop")

    forced_round: int | None = None

    while True:
        async with async_session_maker() as session:
            matcher = MatcherService(session)
            result = await matcher.find_next_match_pair(
                forced_round=forced_round
            )

            match result:
                case MatchFound(match):
                    await session.commit()

                    if match.user_b_id is None:
                        logger.info(
                            "User %s participated in round %d but no match found (no available candidates)",
                            match.user_a_id,
                            match.matching_round,
                        )
                        forced_round = match.matching_round
                        continue

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

                    return

                case RoundExhausted(current_round):
                    new_round = await matcher.advance_round()

                    logger.info(
                        "Round %d complete, starting round %d",
                        current_round,
                        new_round,
                    )
                    forced_round = new_round
                    continue

                case AllUsersMatched():
                    logger.info(
                        "No complete users available, sleeping %d seconds",
                        MATCHING_RETRY_INTERVAL_SECONDS,
                    )
                    forced_round = None
                    await asyncio.sleep(MATCHING_RETRY_INTERVAL_SECONDS)

                case _:
                    logger.warning(
                        "Received unexpected MatchResult type: %r", result
                    )


def start_matching_loop(bot: Bot) -> None:
    """Start the matching loop as a background task."""
    global _matching_task
    _matching_task = asyncio.create_task(run_matching_loop())
    logger.info("Matching loop started")


def stop_matching_loop() -> None:
    """Stop the matching loop gracefully."""
    global _matching_task
    if _matching_task and not _matching_task.done():
        _matching_task.cancel()
        logger.info("Matching loop stopped")
