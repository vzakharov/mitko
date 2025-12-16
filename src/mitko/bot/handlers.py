import json
import re
from uuid import UUID

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import User, Conversation, UserState, get_db
from ..llm import get_llm_provider
from ..services.profiler import ProfileService
from .conversation import SYSTEM_PROMPT, PROFILE_COMPLETE_TOKEN
from .keyboards import match_consent_keyboard

router = Router()

_bot_instance: Bot | None = None


def set_bot_instance(bot: Bot) -> None:
    global _bot_instance
    _bot_instance = bot


def get_bot() -> Bot:
    if _bot_instance is None:
        raise RuntimeError("Bot instance not set")
    return _bot_instance


async def get_or_create_user(telegram_id: int, session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, state="onboarding")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_or_create_conversation(telegram_id: int, session: AsyncSession) -> Conversation:
    result = await session.execute(
        select(Conversation).where(Conversation.telegram_id == telegram_id)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        conv = Conversation(telegram_id=telegram_id, messages=[])
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
    return conv


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    async for session in get_db():
        user = await get_or_create_user(message.from_user.id, session)
        await message.answer(
            "Hi! I'm Mitko, your IT matchmaking assistant. "
            "I'll chat with you to understand what you're looking for, then help connect you with great matches.\n\n"
            "Are you looking for work, or are you hiring?"
        )


@router.message()
async def handle_message(message: Message) -> None:
    if not message.text:
        return

    async for session in get_db():
        user = await get_or_create_user(message.from_user.id, session)
        conv = await get_or_create_conversation(message.from_user.id, session)

        conv.messages.append({"role": "user", "content": message.text})
        await session.commit()

        llm = get_llm_provider()
        response = await llm.chat(conv.messages, SYSTEM_PROMPT)

        if PROFILE_COMPLETE_TOKEN in response:
            parts = response.split(PROFILE_COMPLETE_TOKEN, 1)
            bot_response = parts[0].strip()
            json_part = parts[1].strip()

            try:
                profile_data = json.loads(json_part)
                profiler = ProfileService(session, llm)
                await profiler.create_profile(user, conv, profile_data)
                await message.answer(
                    bot_response + "\n\nGreat! Your profile is complete. "
                    "I'll notify you when I find potential matches."
                )
            except json.JSONDecodeError:
                await message.answer(response)
        else:
            conv.messages.append({"role": "assistant", "content": response})
            await session.commit()
            await message.answer(response)


@router.callback_query(F.data.startswith("match_accept:"))
async def handle_match_accept(callback: CallbackQuery) -> None:
    match_id_str = callback.data.split(":", 1)[1]
    match_id = UUID(match_id_str)

    async for session in get_db():
        from ..models import Match, MatchStatus, Profile

        result = await session.execute(select(Match).where(Match.id == match_id))
        match = result.scalar_one_or_none()
        if not match:
            await callback.answer("Match not found", show_alert=True)
            return

        profile_a_result = await session.execute(
            select(Profile).where(Profile.id == match.profile_a_id)
        )
        profile_b_result = await session.execute(
            select(Profile).where(Profile.id == match.profile_b_id)
        )
        profile_a = profile_a_result.scalar_one()
        profile_b = profile_b_result.scalar_one()

        user_profile = None
        other_profile = None
        if profile_a.telegram_id == callback.from_user.id:
            user_profile = profile_a
            other_profile = profile_b
        elif profile_b.telegram_id == callback.from_user.id:
            user_profile = profile_b
            other_profile = profile_a
        else:
            await callback.answer("You're not authorized for this match", show_alert=True)
            return

        if match.status == "pending":
            match.status = "a_accepted" if user_profile.id == profile_a.id else "b_accepted"
            await session.commit()
            await callback.answer("Thanks! Waiting for the other party to respond.")
        elif match.status in ("a_accepted", "b_accepted"):
            match.status = "connected"
            await session.commit()

            bot = get_bot()
            await bot.send_message(
                profile_a.telegram_id,
                f"🎉 Connection made! Here are the details:\n\n{profile_b.summary}\n\n"
                f"You can now contact them directly.",
            )
            await bot.send_message(
                profile_b.telegram_id,
                f"🎉 Connection made! Here are the details:\n\n{profile_a.summary}\n\n"
                f"You can now contact them directly.",
            )
            await callback.answer("Connected! Check your messages for details.")
        else:
            await callback.answer("This match is already processed", show_alert=True)


@router.callback_query(F.data.startswith("match_reject:"))
async def handle_match_reject(callback: CallbackQuery) -> None:
    match_id_str = callback.data.split(":", 1)[1]
    match_id = UUID(match_id_str)

    async for session in get_db():
        from ..models import Match, MatchStatus

        result = await session.execute(select(Match).where(Match.id == match_id))
        match = result.scalar_one_or_none()
        if not match:
            await callback.answer("Match not found", show_alert=True)
            return

        match.status = "rejected"
        await session.commit()
        await callback.answer("Noted. We'll find better matches for you!")

