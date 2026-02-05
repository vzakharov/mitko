"""Generation service for creating and scheduling LLM generations with budget control.

This module provides a unified entry point for creating generations with automatic
budget-aware scheduling. It handles:
- Budget interval calculation based on previous generation costs
- Proper queueing (sequential, respects max_scheduled_for)
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..config import SETTINGS
from ..jobs.generation import nudge_processor
from ..models import Generation


async def _get_max_scheduled_time(session: AsyncSession) -> datetime | None:
    """Get the maximum scheduled_for time across all generations."""
    result = await session.execute(
        select(sql_func.max(Generation.scheduled_for))
    )
    return result.scalar_one_or_none()


async def _calculate_budget_interval(session: AsyncSession) -> timedelta:
    """Calculate dynamic generation interval based on weekly budget.

    Uses the cost of the most recently started generation to estimate spacing.
    If no previous generation with cost exists, returns 0 (no delay).
    """
    result = await session.execute(
        select(Generation)
        .where(col(Generation.started_at).isnot(None))
        .where(col(Generation.cost_usd).isnot(None))
        .order_by(col(Generation.started_at).desc())
        .limit(1)
    )
    last_gen = result.scalar_one_or_none()

    if last_gen is None or last_gen.cost_usd is None:
        return timedelta(seconds=0)

    seconds_per_week = 7 * 24 * 3600
    interval_seconds = (
        last_gen.cost_usd * seconds_per_week
    ) / SETTINGS.weekly_budget_usd

    return timedelta(seconds=interval_seconds)


async def create_generation(
    session: AsyncSession,
    conversation_id: uuid.UUID,
) -> Generation:
    """Create a new generation with budget-adjusted scheduling.

    This function should be used by ANY code that wants to queue an LLM generation.
    It handles:
    - Budget interval calculation based on previous generation costs
    - Proper queueing (sequential, respects max_scheduled_for)
    """
    interval = await _calculate_budget_interval(session)

    max_scheduled = await _get_max_scheduled_time(session)

    now = datetime.now(UTC)
    if max_scheduled is not None:
        scheduled_for = max_scheduled + interval
    else:
        scheduled_for = now

    generation = Generation(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        scheduled_for=scheduled_for,
        status="pending",
        created_at=now,
    )
    session.add(generation)
    await session.commit()
    await session.refresh(generation)

    nudge_processor()

    return generation
