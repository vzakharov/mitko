"""Matching scheduler: queue-based single-match processing."""

import asyncio
import logging

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
    5. Stops when a full round produces no real matches (externally restarted when needed)
    """
    from ..bot.bot_instance import get_bot
    from ..bot.utils import format_user_label
    from ..db import get_user
    from ..i18n import L
    from ..services.admin_group import mirror_to_admin_thread

    logger.info("Starting matching loop")

    forced_round: int | None = None
    matched_in_round = False

    while True:
        async with async_session_maker() as session:
            matcher = MatcherService(session)
            result = await matcher.find_next_match_pair(
                forced_round=forced_round
            )

            match result:
                case MatchFound(match):
                    user_a = await get_user(session, match.user_a_id)

                    async def mirror(message: str) -> None:
                        await mirror_to_admin_thread(
                            get_bot(),
                            match.user_a_id,
                            message,
                            session,
                        )

                    await mirror(
                        L.admin.matching.SEARCHING.format(
                            label=format_user_label(user_a)
                        )
                    )

                    await session.commit()

                    if match.user_b_id is None:
                        await mirror(L.admin.matching.NOT_FOUND)

                        logger.info(
                            "User %s participated in round %d but no match found (no available candidates)",
                            match.user_a_id,
                            match.matching_round,
                        )
                        forced_round = match.matching_round
                        continue

                    user_b = await get_user(session, match.user_b_id)
                    await mirror(
                        L.admin.matching.FOUND.format(
                            label=format_user_label(user_b),
                            score=match.similarity_score,
                        )
                    )

                    matched_in_round = True
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
                    if not matched_in_round:
                        logger.info(
                            "Round %d had no matches; stopping loop",
                            current_round,
                        )
                        return

                    new_round = await matcher.advance_round()

                    logger.info(
                        "Round %d complete, starting round %d",
                        current_round,
                        new_round,
                    )
                    matched_in_round = False
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


def start_matching_loop() -> None:
    """Start the matching loop as a background task."""
    global _matching_task
    if _matching_task and not _matching_task.done():
        logger.info("Matching loop already running, ignoring start request")
        return
    _matching_task = asyncio.create_task(run_matching_loop())
    logger.info("Matching loop started")


def stop_matching_loop() -> None:
    """Stop the matching loop gracefully."""
    global _matching_task
    if _matching_task and not _matching_task.done():
        _matching_task.cancel()
        logger.info("Matching loop stopped")
