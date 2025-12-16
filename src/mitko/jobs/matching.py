from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import async_session_maker, Match, Profile
from ..services.matcher import MatcherService
from ..llm import get_llm_provider
from ..config import settings
from ..bot.keyboards import match_consent_keyboard

scheduler = AsyncIOScheduler()


async def run_matching_job(bot: Bot) -> None:
    async with async_session_maker() as session:
        llm = get_llm_provider()
        matcher = MatcherService(session, llm)
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

    message_a = (
        f"🎯 Found a potential match!\n\n"
        f"{profile_b.summary}\n\n"
        f"💡 Why this match: {match.match_rationale}\n\n"
        f"Would you like to connect?"
    )

    message_b = (
        f"🎯 Found a potential match!\n\n"
        f"{profile_a.summary}\n\n"
        f"💡 Why this match: {match.match_rationale}\n\n"
        f"Would you like to connect?"
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

