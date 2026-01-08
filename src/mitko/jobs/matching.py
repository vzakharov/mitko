from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..bot.keyboards import match_consent_keyboard
from ..config import settings
from ..i18n import L
from ..models import Match, Profile, async_session_maker
from ..services.matcher import MatcherService

scheduler = AsyncIOScheduler()


async def run_matching_job(bot: Bot) -> None:
    async with async_session_maker() as session:
        matcher = MatcherService(session)
        matches = await matcher.find_matches()

        for match in matches:
            await notify_match(bot, match, session)


async def notify_match(bot: Bot, match: Match, session: AsyncSession) -> None:
    profile_a_result = await session.execute(
        select(Profile).where(Profile.id == match.profile_a_id)
    )
    profile_b_result = await session.execute(
        select(Profile).where(Profile.id == match.profile_b_id)
    )
    profile_a = profile_a_result.scalar_one()
    profile_b = profile_b_result.scalar_one()

    message_a = L.matching.FOUND.format(
        profile=profile_b.summary, rationale=match.match_rationale
    )

    message_b = L.matching.FOUND.format(
        profile=profile_a.summary, rationale=match.match_rationale
    )

    keyboard = match_consent_keyboard(match.id)

    await bot.send_message(profile_a.telegram_id, message_a, reply_markup=keyboard)
    await bot.send_message(profile_b.telegram_id, message_b, reply_markup=keyboard)


def start_matching_scheduler(bot: Bot) -> None:
    scheduler.add_job(
        run_matching_job,
        "interval",
        minutes=settings.matching_interval_minutes,
        args=[bot],
        id="matching_job",
        replace_existing=True,
    )
    scheduler.start()


def stop_matching_scheduler() -> None:
    """Stop the scheduler gracefully"""
    if scheduler.running:
        scheduler.shutdown(wait=True)

