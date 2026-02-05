"""Generation orchestrator service for creating, scheduling, and managing LLM generations.

This module provides CRUD operations and budget-aware scheduling for generations.
It handles:
- Budget interval calculation based on previous generation costs
- Proper queueing (sequential, respects max_scheduled_for)
- Fetching pending generations for processing
- Marking generations as started/completed/failed
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..config import SETTINGS
from ..models import Generation


class GenerationOrchestrator:
    """Orchestrator for managing LLM generation lifecycle."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_generation(
        self,
        conversation_id: uuid.UUID,
    ) -> Generation:
        """Create a new generation with budget-adjusted scheduling.

        This function should be used by ANY code that wants to queue an LLM generation.
        It handles:
        - Budget interval calculation based on previous generation costs
        - Proper queueing (sequential, respects max_scheduled_for)
        """
        interval = await self._calculate_budget_interval()
        max_scheduled = await self._get_max_scheduled_time()

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
        self.session.add(generation)
        await self.session.commit()
        await self.session.refresh(generation)

        return generation

    async def get_next_pending(self) -> Generation | None:
        """Find the pending generation with earliest scheduled_for <= now."""
        return (
            await self.session.execute(
                select(Generation)
                .where(col(Generation.status) == "pending")
                .where(col(Generation.scheduled_for) <= datetime.now(UTC))
                .order_by(col(Generation.scheduled_for).asc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def get_next_scheduled_time(self) -> datetime | None:
        """Get the earliest pending scheduled_for time (for wait calculation)."""
        return (
            await self.session.execute(
                select(sql_func.min(Generation.scheduled_for)).where(
                    col(Generation.status) == "pending"
                )
            )
        ).scalar_one_or_none()

    async def mark_started(self, generation: Generation) -> None:
        """Mark generation as started."""
        generation.status = "started"
        generation.started_at = datetime.now(UTC)
        await self.session.commit()

    async def mark_completed(self, generation: Generation) -> None:
        """Mark generation as completed."""
        generation.status = "completed"
        await self.session.commit()

    async def mark_failed(self, generation: Generation) -> None:
        """Mark generation as failed."""
        generation.status = "failed"
        await self.session.commit()

    async def _get_max_scheduled_time(self) -> datetime | None:
        """Get the maximum scheduled_for time across all generations."""
        return (
            await self.session.execute(
                select(sql_func.max(Generation.scheduled_for))
            )
        ).scalar_one_or_none()

    async def _calculate_budget_interval(self) -> timedelta:
        """Calculate dynamic generation interval based on weekly budget.

        Uses the cost of the most recently started generation to estimate spacing.
        If no previous generation with cost exists, returns 0 (no delay).
        """
        last_gen = (
            await self.session.execute(
                select(Generation)
                .where(col(Generation.started_at).isnot(None))
                .where(col(Generation.cost_usd).isnot(None))
                .order_by(col(Generation.started_at).desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if last_gen is None or last_gen.cost_usd is None:
            return timedelta(seconds=0)

        seconds_per_week = 7 * 24 * 3600
        interval_seconds = (
            last_gen.cost_usd * seconds_per_week
        ) / SETTINGS.weekly_budget_usd

        return timedelta(seconds=interval_seconds)
