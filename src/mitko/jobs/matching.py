from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..bot.keyboards import match_consent_keyboard
from ..config import SETTINGS
from ..i18n import L
from ..models import Match, User, async_session_maker
from ..services.matcher import MatcherService

scheduler = AsyncIOScheduler()


async def run_matching_job(bot: Bot) -> None:
    async with async_session_maker() as session:
        matcher = MatcherService(session)
        matches = await matcher.find_matches()

        for match in matches:
            await notify_match(bot, match, session)


def _format_profile_for_display(user: User) -> str:
    """Combine matching_summary + practical_context for display"""
    parts = [user.matching_summary or ""]
    if user.practical_context:
        parts.append(user.practical_context)
    return "\n\n".join(parts)


async def notify_match(bot: Bot, match: Match, session: AsyncSession) -> None:
    user_a_result = await session.execute(
        select(User).where(col(User.telegram_id) == match.user_a_id)
    )
    user_b_result = await session.execute(
        select(User).where(col(User.telegram_id) == match.user_b_id)
    )
    user_a = user_a_result.scalar_one()
    user_b = user_b_result.scalar_one()

    profile_display_a = _format_profile_for_display(user_b)
    profile_display_b = _format_profile_for_display(user_a)

    message_a = L.matching.FOUND.format(
        profile=profile_display_a, rationale=match.match_rationale
    )

    message_b = L.matching.FOUND.format(
        profile=profile_display_b, rationale=match.match_rationale
    )

    keyboard = match_consent_keyboard(match.id)

    await bot.send_message(user_a.telegram_id, message_a, reply_markup=keyboard)
    await bot.send_message(user_b.telegram_id, message_b, reply_markup=keyboard)


def start_matching_scheduler(bot: Bot) -> None:
    scheduler.add_job(
        run_matching_job,
        "interval",
        minutes=SETTINGS.matching_interval_minutes,
        args=[bot],
        id="matching_job",
        replace_existing=True,
    )
    scheduler.start()


def stop_matching_scheduler() -> None:
    """Stop the scheduler gracefully"""
    if scheduler.running:
        scheduler.shutdown(wait=True)
