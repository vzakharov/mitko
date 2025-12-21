from uuid import UUID

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import User, Conversation, get_db
from ..services.profiler import ProfileService
from ..agents import ConversationAgent, ProfileData, get_model_name
from .keyboards import reset_confirmation_keyboard, MatchAction, ResetAction

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


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    """Handler for /reset command - shows confirmation dialog"""
    async for session in get_db():
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await message.answer(
                "You don't have an active profile yet. Use /start to begin!"
            )
            return

        warning_message = (
            "⚠️ Reset Your Profile\n\n"
            "This will permanently:\n"
            "• Delete your profile information\n"
            "• Clear your conversation history\n"
            "• Return you to the onboarding process\n\n"
            "Your existing matches will be preserved.\n\n"
            "Are you sure you want to continue?"
        )

        await message.answer(
            warning_message,
            reply_markup=reset_confirmation_keyboard(message.from_user.id)
        )


def _format_profile_card(profile: ProfileData) -> str:
    """Format profile as a user-visible card"""
    card_parts = ["📋 Your Profile:\n"]

    # Role
    roles = []
    if profile.is_seeker:
        roles.append("Job Seeker")
    if profile.is_provider:
        roles.append("Hiring/Providing")
    card_parts.append(f"Role: {' & '.join(roles)}")

    # Summary
    card_parts.append(f"\n\n{profile.summary}")

    return "".join(card_parts)


@router.message()
async def handle_message(message: Message) -> None:
    if not message.text:
        return

    async for session in get_db():
        user = await get_or_create_user(message.from_user.id, session)
        conv = await get_or_create_conversation(message.from_user.id, session)

        # Add user message
        conv.messages.append({"role": "user", "content": message.text})
        await session.commit()

        # Use unified conversation agent
        conversation_agent = ConversationAgent(get_model_name())

        # Prepare existing profile for updates
        existing_profile = None
        if user.is_complete and user.summary:
            existing_profile = ProfileData(
                is_seeker=user.is_seeker or False,
                is_provider=user.is_provider or False,
                summary=user.summary
            )

        # Get response from agent
        response = await conversation_agent.chat(conv.messages, existing_profile)

        # Handle profile creation/update
        if response.profile:
            profiler = ProfileService(session)
            is_update = user.is_complete

            await profiler.create_or_update_profile(
                user,
                response.profile,
                is_update=is_update
            )

            # Show profile card to user
            profile_card = _format_profile_card(response.profile)
            await message.answer(f"{response.utterance}\n\n{profile_card}")
        else:
            # Just send the utterance
            await message.answer(response.utterance)

        # Store assistant response
        conv.messages.append({"role": "assistant", "content": response.utterance})
        await session.commit()


@router.callback_query(MatchAction.filter(F.action == "accept"))
async def handle_match_accept(callback: CallbackQuery, callback_data: MatchAction) -> None:
    match_id = UUID(callback_data.match_id)

    async for session in get_db():
        from ..models import Match, MatchStatus

        result = await session.execute(select(Match).where(Match.id == match_id))
        match = result.scalar_one_or_none()
        if not match:
            await callback.answer("Match not found", show_alert=True)
            return

        user_a_result = await session.execute(
            select(User).where(User.telegram_id == match.user_a_id)
        )
        user_b_result = await session.execute(
            select(User).where(User.telegram_id == match.user_b_id)
        )
        user_a = user_a_result.scalar_one()
        user_b = user_b_result.scalar_one()

        current_user = None
        other_user = None
        if user_a.telegram_id == callback.from_user.id:
            current_user = user_a
            other_user = user_b
        elif user_b.telegram_id == callback.from_user.id:
            current_user = user_b
            other_user = user_a
        else:
            await callback.answer("You're not authorized for this match", show_alert=True)
            return

        if match.status == "pending":
            match.status = "a_accepted" if current_user.telegram_id == user_a.telegram_id else "b_accepted"
            await session.commit()
            await callback.answer("Thanks! Waiting for the other party to respond.")
        elif match.status in ("a_accepted", "b_accepted"):
            match.status = "connected"
            await session.commit()

            bot = get_bot()
            await bot.send_message(
                user_a.telegram_id,
                f"🎉 Connection made! Here are the details:\n\n{user_b.summary}\n\n"
                f"You can now contact them directly.",
            )
            await bot.send_message(
                user_b.telegram_id,
                f"🎉 Connection made! Here are the details:\n\n{user_a.summary}\n\n"
                f"You can now contact them directly.",
            )
            await callback.answer("Connected! Check your messages for details.")
        else:
            await callback.answer("This match is already processed", show_alert=True)


@router.callback_query(MatchAction.filter(F.action == "reject"))
async def handle_match_reject(callback: CallbackQuery, callback_data: MatchAction) -> None:
    match_id = UUID(callback_data.match_id)

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


@router.callback_query(ResetAction.filter(F.action == "confirm"))
async def handle_reset_confirm(callback: CallbackQuery, callback_data: ResetAction) -> None:
    """Handler for reset confirmation button"""
    telegram_id = callback_data.telegram_id

    # Authorization check
    if callback.from_user.id != telegram_id:
        await callback.answer(
            "You're not authorized for this action",
            show_alert=True
        )
        return

    async for session in get_db():
        # Get user and conversation
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("User not found", show_alert=True)
            return

        conv_result = await session.execute(
            select(Conversation).where(Conversation.telegram_id == telegram_id)
        )
        conversation = conv_result.scalar_one_or_none()

        # Use ProfileService to reset
        profiler = ProfileService(session)
        await profiler.reset_profile(user, conversation)

        # Send success message
        await callback.message.edit_text(
            "✅ Profile Reset Complete\n\n"
            "Your profile and conversation history have been cleared.\n"
            "You're now back at the beginning.\n\n"
            "Ready to start fresh? Tell me: are you looking for work, or are you hiring?"
        )

        await callback.answer()


@router.callback_query(ResetAction.filter(F.action == "cancel"))
async def handle_reset_cancel(callback: CallbackQuery, callback_data: ResetAction) -> None:
    """Handler for reset cancellation button"""
    telegram_id = callback_data.telegram_id

    # Authorization check
    if callback.from_user.id != telegram_id:
        await callback.answer(
            "You're not authorized for this action",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "Reset cancelled. Your profile remains unchanged."
    )
    await callback.answer()

