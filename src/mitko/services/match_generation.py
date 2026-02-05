"""Match generation service for LLM-powered match rationale generation."""

import logging
from dataclasses import dataclass
from textwrap import dedent
from typing import TYPE_CHECKING

from aiogram import Bot
from genai_prices import calc_price
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..agents.config import LANGUAGE_MODEL
from ..agents.rationale_agent import RATIONALE_AGENT
from ..bot.keyboards import match_consent_keyboard
from ..config import SETTINGS
from ..i18n import L
from ..models import Match, User

if TYPE_CHECKING:
    from pydantic_ai.run import AgentRunResult

    from ..agents.rationale_agent import MatchRationale
    from ..models import Generation

logger = logging.getLogger(__name__)


def _format_profile_for_display(user: User) -> str:
    """Combine matching_summary + practical_context for display."""
    parts = [user.matching_summary or ""]
    if user.practical_context:
        parts.append(user.practical_context)
    return "\n\n".join(parts)


@dataclass
class MatchGeneration:
    """Service for processing match generations."""

    bot: Bot
    session: AsyncSession
    generation: "Generation"
    match: Match

    async def execute(self) -> None:
        """Process a match generation: generate rationale, notify users, enqueue next match."""

        try:
            # Fetch both users
            user_a, user_b = await self._fetch_users()

            # Generate rationale
            rationale_text = await self._generate_match_rationale(
                user_a, user_b
            )
            self.match.match_rationale = rationale_text

            # Notify both users
            await self._notify_both_users(user_a, user_b, rationale_text)

            await self.session.commit()

            logger.info(
                "Processed match generation %s: notified users %s and %s",
                self.generation.id,
                user_a.telegram_id,
                user_b.telegram_id,
            )

        except Exception:
            logger.exception(
                "Match generation %s failed for match %s",
                self.generation.id,
                self.match.id,
            )
            raise
        finally:
            # Always restart matching loop (whether successful or not)
            await self._restart_matching_loop()

    async def _fetch_users(self) -> tuple[User, User]:
        """Fetch both users involved in the match."""
        user_a_result = await self.session.execute(
            select(User).where(col(User.telegram_id) == self.match.user_a_id)
        )
        user_b_result = await self.session.execute(
            select(User).where(col(User.telegram_id) == self.match.user_b_id)
        )
        user_a = user_a_result.scalar_one()
        user_b = user_b_result.scalar_one()
        return user_a, user_b

    async def _generate_match_rationale(
        self, user_a: User, user_b: User
    ) -> str:
        """Generate match rationale using RATIONALE_AGENT."""

        # Build profile sections
        user_a_profile = f"""Technical Background: {user_a.matching_summary or "Not provided"}
Work Preferences: {user_a.practical_context or "Not yet specified"}
Internal Notes: {user_a.private_observations or "None"}"""

        user_b_profile = f"""Technical Background: {user_b.matching_summary or "Not provided"}
Work Preferences: {user_b.practical_context or "Not yet specified"}
Internal Notes: {user_b.private_observations or "None"}"""

        prompt = dedent(
            f"""Analyze these two profiles and explain why they're a good match:

            User A Profile:
            {user_a_profile}

            User B Profile:
            {user_b_profile}

            Generate a structured match rationale considering:
            - Technical alignment (skills, experience, domain expertise)
            - Practical compatibility (location, remote preference, availability) - if specified
            - Potential concerns from internal notes (if any - use these to inform confidence scoring)

            Important: Internal notes are for YOUR evaluation only. Do not mention them explicitly in the
            explanation shown to users. If they raise concerns, reflect that in a lower confidence_score
            and focus on genuine alignments in your explanation.

            Note: Work Preferences may be "Not yet specified" for some users during a transition period.
            Focus on technical alignment in such cases.

            Output:
            - explanation: A brief, friendly 2-3 sentence explanation of technical + practical fit
            - key_alignments: A list of 2-4 specific points where they align (focus on technical if practical missing)
            - confidence_score: A score from 0.0 to 1.0 (adjust down if internal notes raise concerns or if practical context is missing)"""
        )

        result = await RATIONALE_AGENT.run(prompt)
        rationale = result.output

        # Record usage and cost
        self._record_usage_and_cost(result)

        # Format for display (only explanation and key_alignments are shown to users)
        formatted = [rationale.explanation]
        if rationale.key_alignments:
            formatted.append("\n\nKey alignments:")
            for alignment in rationale.key_alignments:
                formatted.append(f"\n• {alignment}")

        return "".join(formatted)

    async def _notify_both_users(
        self, user_a: User, user_b: User, rationale: str
    ) -> None:
        """Send match notifications to both users."""
        profile_display_a = _format_profile_for_display(user_b)
        profile_display_b = _format_profile_for_display(user_a)

        message_a = L.matching.FOUND.format(
            profile=profile_display_a, rationale=rationale
        )
        message_b = L.matching.FOUND.format(
            profile=profile_display_b, rationale=rationale
        )

        keyboard = match_consent_keyboard(self.match.id)

        await self.bot.send_message(
            user_a.telegram_id, message_a, reply_markup=keyboard
        )
        await self.bot.send_message(
            user_b.telegram_id, message_b, reply_markup=keyboard
        )

    def _record_usage_and_cost(
        self,
        result: "AgentRunResult[MatchRationale]",
    ) -> None:
        """Record token usage and calculate cost."""
        usage = result.usage()
        gen = self.generation
        gen.cached_input_tokens = usage.cache_read_tokens
        gen.uncached_input_tokens = usage.input_tokens - usage.cache_read_tokens
        gen.output_tokens = usage.output_tokens

        # Calculate cost using genai-prices
        try:
            price_data = calc_price(
                usage,
                model_ref=LANGUAGE_MODEL.model_name,
                provider_id=SETTINGS.llm_provider,
            )
            gen.cost_usd = float(price_data.total_price)

            logger.info(
                "Match generation %s: cost=$%.4f (input=%d cached=%d output=%d)",
                gen.id,
                gen.cost_usd,
                gen.uncached_input_tokens or 0,
                gen.cached_input_tokens or 0,
                gen.output_tokens or 0,
            )
        except Exception:
            logger.exception(
                "Failed to calculate cost for match generation %s", gen.id
            )
            gen.cost_usd = 0.0

    async def _restart_matching_loop(self) -> None:
        """Restart the matching loop to find the next match."""
        from ..jobs.matching_scheduler import start_matching_loop

        start_matching_loop(self.bot)
        logger.info(
            "Restarted matching loop after generation %s", self.generation.id
        )
