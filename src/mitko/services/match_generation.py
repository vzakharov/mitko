"""Match generation service for LLM-powered match rationale generation."""

import asyncio
import logging
from dataclasses import dataclass
from textwrap import dedent
from typing import TYPE_CHECKING, Literal

from aiogram import Bot
from genai_prices import calc_price
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.config import LANGUAGE_MODEL
from ..agents.qualifier_agent import QUALIFIER_AGENT
from ..bot.keyboards import match_consent_keyboard
from ..config import SETTINGS
from ..db import get_user
from ..i18n import L
from ..models import Match, User
from ..utils.typing_utils import raise_error
from .chat_utils import send_to_user

if TYPE_CHECKING:
    from pydantic_ai.run import AgentRunResult

    from ..agents.qualifier_agent import MatchQualification
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
        """Process a match generation: generate rationale, update status, notify users if qualified."""

        try:
            # Fetch both users
            user_a, user_b = await self._fetch_users()

            # Generate rationale and decision
            explanation, decision = await self._generate_match_rationale(
                user_a, user_b
            )

            # Store explanation (internal reasoning) and update status based on decision
            self.match.match_rationale = explanation
            self.match.status = decision

            await self.session.commit()

            # Only notify users if match is qualified
            if decision == "qualified":
                # TODO: Create MatchSuggesterAgent to convert internal explanation into
                # natural user-facing messages like "Hey Bob, we figured you might want to
                # talk to Alice, she's ..." For now, showing internal explanation directly.
                # TODO: Implement safeguards to prevent red flag information from leaking
                # between users in the explanation.
                await self._notify_both_users(user_a, user_b, explanation)

            logger.info(
                "Processed match generation %s: decision=%s for users %s and %s",
                self.generation.id,
                decision,
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
        (user_a, user_b) = await asyncio.gather(
            *(
                get_user(self.session, id)
                for id in (
                    self.match.user_a_id,
                    self.match.user_b_id
                    or raise_error(ValueError("Match has no user_b_id")),
                )
            )
        )
        return user_a, user_b

    async def _generate_match_rationale(
        self, user_a: User, user_b: User
    ) -> tuple[str, Literal["qualified", "disqualified"]]:
        """Generate match rationale and decision using QUALIFIER_AGENT.

        Returns:
            Tuple of (explanation, decision) where decision is "qualified" or "disqualified"
        """

        # Build profile sections
        user_a_profile = f"""Technical Background: {user_a.matching_summary or "Not provided"}
Work Preferences: {user_a.practical_context or "Not yet specified"}
Internal Notes: {user_a.private_observations or "None"}"""

        user_b_profile = f"""Technical Background: {user_b.matching_summary or "Not provided"}
Work Preferences: {user_b.practical_context or "Not yet specified"}
Internal Notes: {user_b.private_observations or "None"}"""

        prompt = dedent(
            f"""Evaluate this potential match:

            User A Profile:
            {user_a_profile}

            User B Profile:
            {user_b_profile}

            Decide if this match should be qualified (strong enough to present to users) or
            disqualified (not strong enough). Provide your internal reasoning."""
        )

        result = await QUALIFIER_AGENT.run(prompt)
        rationale = result.output

        # Record usage and cost
        self._record_usage_and_cost(result)

        return rationale.explanation, rationale.decision

    async def _notify_both_users(
        self, user_a: User, user_b: User, rationale: str
    ) -> None:
        """Send match notifications to both users."""

        await asyncio.gather(
            *(
                send_to_user(
                    self.bot,
                    user.telegram_id,
                    L.matching.FOUND.format(
                        profile=_format_profile_for_display(
                            user_b if user == user_a else user_a
                        ),
                        rationale=rationale,
                    ),
                    self.session,
                    reply_markup=match_consent_keyboard(self.match.id),
                )
                for user in (user_a, user_b)
            )
        )

    def _record_usage_and_cost(
        self,
        result: "AgentRunResult[MatchQualification]",
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

        logger.info(
            "Restarting matching loop after generation %s", self.generation.id
        )
        start_matching_loop()
