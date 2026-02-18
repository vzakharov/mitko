"""Match generation service for LLM-powered match rationale generation."""

import asyncio
import logging
from dataclasses import dataclass
from textwrap import dedent
from typing import Literal

from ..agents.qualifier_agent import QUALIFIER_AGENT, MatchQualification
from ..bot.keyboards import match_consent_keyboard
from ..config import SETTINGS
from ..db import get_chat, get_user
from ..i18n import L
from ..models import Match, User
from ..services.match_intro_generation import (
    MATCH_INTRO_SYSTEM_MESSAGE_TEMPLATE,
)
from ..types.messages import says
from ..utils.typing_utils import raise_error
from .base_generation import BaseGenerationService
from .chat_utils import send_to_user
from .generation_orchestrator import GenerationOrchestrator

logger = logging.getLogger(__name__)


def _format_profile_for_display(user: User) -> str:
    """Combine matching_summary + practical_context for display."""
    parts = [user.matching_summary or ""]
    if user.practical_context:
        parts.append(user.practical_context)
    return "\n\n".join(parts)


@dataclass
class MatchGeneration(BaseGenerationService[MatchQualification]):
    """Service for processing match generations."""

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
                await (
                    self._notify_users_hardcoded
                    if SETTINGS.use_hardcoded_match_intros
                    else self._create_intro_generations
                )(user_a, user_b, explanation)

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
        self.record_usage_and_cost(result, "match generation")

        return rationale.explanation, rationale.decision

    async def _create_intro_generations(
        self, user_a: User, user_b: User, rationale: str
    ) -> None:
        """Create match intro generations for both users."""
        from ..jobs.generation_processor import nudge_processor

        for user, matched_user in [(user_a, user_b), (user_b, user_a)]:
            chat = await get_chat(self.session, user.telegram_id)

            # Inject system message with match context into history
            # NOTE: This persists in the database via commit() below
            # Future conversations will see this system message in history
            chat.message_history = [
                *chat.message_history,
                says.system(
                    MATCH_INTRO_SYSTEM_MESSAGE_TEMPLATE.format(
                        profile_display=_format_profile_for_display(
                            matched_user
                        ),
                        rationale=rationale,
                    )
                ),
            ]

            # Create generation with BOTH chat_id AND match_id
            # This routes to MatchIntroGeneration (not ChatGeneration)
            await GenerationOrchestrator(self.session).create_generation(
                chat_id=chat.id, match_id=self.match.id
            )

        # Commit persists BOTH the system messages AND the generations
        await self.session.commit()
        nudge_processor()

    async def _notify_users_hardcoded(
        self, user_a: User, user_b: User, rationale: str
    ) -> None:
        """Send match notifications with raw rationale (legacy behavior)."""

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

    async def _restart_matching_loop(self) -> None:
        """Restart the matching loop to find the next match."""
        from ..jobs.matching_scheduler import start_matching_loop

        logger.info(
            "Restarting matching loop after generation %s", self.generation.id
        )
        start_matching_loop()
