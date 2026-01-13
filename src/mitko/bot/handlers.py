import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InaccessibleMessage, Message
from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..config import settings
from ..i18n import L
from ..jobs.generation import nudge_processor
from ..models import Conversation, Generation, User, get_db
from ..services.profiler import ProfileService
from ..types import UserMessage
from .keyboards import MatchAction, ResetAction, reset_confirmation_keyboard

router = Router()
logger = logging.getLogger(__name__)

# Delay before nudging processor to allow rapid successive messages to be processed
# (e.g., long messages split by Telegram into multiple parts)
NUDGE_DELAY_SECONDS = 1.0

_bot_instance: Bot | None = None


def set_bot_instance(bot: Bot) -> None:
    global _bot_instance
    _bot_instance = bot


def get_bot() -> Bot:
    if _bot_instance is None:
        raise RuntimeError("Bot instance not set")
    return _bot_instance


async def validate_callback_message(callback: CallbackQuery) -> Message | None:
    """
    Validate callback.message is accessible and return it, or send error and return None.

    Returns:
        Message if accessible, None if inaccessible (error already sent to user)
    """
    if callback.message is None or isinstance(
        callback.message, InaccessibleMessage
    ):
        await callback.answer(
            L.system.errors.MESSAGE_UNAVAILABLE, show_alert=True
        )
        return None
    return callback.message


async def get_or_create_user(telegram_id: int, session: AsyncSession) -> User:
    result = await session.execute(
        select(User).where(col(User.telegram_id) == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, state="onboarding")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_or_create_conversation(
    telegram_id: int, session: AsyncSession
) -> Conversation:
    result = await session.execute(
        select(Conversation).where(col(Conversation.telegram_id) == telegram_id)
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
    if message.from_user is None:
        return
    async for session in get_db():
        user = await get_or_create_user(message.from_user.id, session)
        conv = await get_or_create_conversation(message.from_user.id, session)

        # Check if user has ANY existing data
        has_data = (
            user.summary is not None
            or user.is_seeker is not None
            or user.is_provider is not None
            or len(conv.messages) > 0
        )

        if has_data:
            # Existing user - show reset warning with confirmation keyboard
            await message.answer(
                L.commands.reset.WARNING,
                reply_markup=reset_confirmation_keyboard(message.from_user.id),
            )
        else:
            # New user - just send greeting and initialize with empty history
            await message.answer(L.commands.start.GREETING)
            # Start with empty conversation history (greeting is in system prompt)
            conv.messages = []
            await session.commit()
            logger.info(
                "Started conversation for user %d: empty history",
                message.from_user.id,
            )


async def _get_max_scheduled_time(session: AsyncSession) -> datetime | None:
    """Get the maximum scheduled_for time across all generations."""
    result = await session.execute(
        select(sql_func.max(Generation.scheduled_for))
    )
    return result.scalar_one_or_none()


async def _has_pending_generation(
    conversation_id: uuid.UUID, session: AsyncSession
) -> bool:
    """Check if conversation has a pending generation."""
    result = await session.execute(
        select(Generation)
        .where(col(Generation.conversation_id) == conversation_id)
        .where(col(Generation.status) == "pending")
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _delayed_nudge() -> None:
    """Delay nudge to allow rapid successive messages to be processed first."""
    await asyncio.sleep(NUDGE_DELAY_SECONDS)
    nudge_processor()


@router.message()
async def handle_message(message: Message) -> None:
    if not message.text or message.from_user is None:
        return

    async for session in get_db():
        await get_or_create_user(message.from_user.id, session)
        conv = await get_or_create_conversation(message.from_user.id, session)

        # Add user message
        conv.messages.append(UserMessage.create(message.text))

        # Acquire exclusive lock on conversation row to prevent race conditions
        # when multiple messages arrive simultaneously (e.g., long messages split by Telegram)
        await session.execute(
            select(Conversation)
            .where(col(Conversation.id) == conv.id)
            .with_for_update()
        )

        # Check if there's already a pending generation for this conversation
        has_pending = await _has_pending_generation(conv.id, session)

        if has_pending:
            # Message will be included in the pending generation's context
            await session.commit()
            logger.info(
                "Stored user message for %d: %d total messages (pending generation exists)",
                message.from_user.id,
                len(conv.messages),
            )
        else:
            # Create a new generation
            now = datetime.now(UTC)
            interval = timedelta(seconds=settings.generation_interval_seconds)

            # Find max scheduled time to maintain global queue order
            max_scheduled = await _get_max_scheduled_time(session)

            if max_scheduled is not None:
                # Add interval to max (even if in the past - for budget control)
                scheduled_for = max_scheduled + interval
            else:
                # No generations exist - schedule for now
                scheduled_for = now

            generation = Generation(
                conversation_id=conv.id,
                scheduled_for=scheduled_for,
            )
            session.add(generation)
            await session.commit()

            # Send acknowledgment with estimated reply time
            reply_time = scheduled_for.strftime("%H:%M:%S")
            await message.answer(
                L.system.SCHEDULED_REPLY.format(time=reply_time)
            )

            logger.info(
                "Stored user message for %d: %d total messages, scheduled_for=%s",
                message.from_user.id,
                len(conv.messages),
                scheduled_for,
            )

            # Nudge processor after a short delay to allow rapid successive messages
            # to be processed first (e.g., long messages split by Telegram)
            asyncio.create_task(_delayed_nudge())


@router.callback_query(MatchAction.filter(F.action == "accept"))
async def handle_match_accept(
    callback: CallbackQuery, callback_data: MatchAction
) -> None:
    match_id = UUID(callback_data.match_id)

    async for session in get_db():
        from ..models import Match

        result = await session.execute(
            select(Match).where(col(Match.id) == match_id)
        )
        match = result.scalar_one_or_none()
        if not match:
            await callback.answer(L.matching.errors.NOT_FOUND, show_alert=True)
            return

        user_a_result = await session.execute(
            select(User).where(col(User.telegram_id) == match.user_a_id)
        )
        user_b_result = await session.execute(
            select(User).where(col(User.telegram_id) == match.user_b_id)
        )
        user_a = user_a_result.scalar_one()
        user_b = user_b_result.scalar_one()

        current_user = None
        if user_a.telegram_id == callback.from_user.id:
            current_user = user_a
        elif user_b.telegram_id == callback.from_user.id:
            current_user = user_b
        else:
            await callback.answer(
                L.matching.errors.UNAUTHORIZED, show_alert=True
            )
            return

        if match.status == "pending":
            is_user_a = current_user.telegram_id == user_a.telegram_id
            match.status = "a_accepted" if is_user_a else "b_accepted"
            await session.commit()
            await callback.answer(L.matching.ACCEPT_WAITING)
        elif match.status in ("a_accepted", "b_accepted"):
            match.status = "connected"
            await session.commit()

            bot = get_bot()
            await bot.send_message(
                user_a.telegram_id,
                L.matching.CONNECTION_MADE.format(profile=user_b.summary),
            )
            await bot.send_message(
                user_b.telegram_id,
                L.matching.CONNECTION_MADE.format(profile=user_a.summary),
            )
            await callback.answer(L.matching.ACCEPT_CONNECTED)
        else:
            await callback.answer(
                L.matching.errors.ALREADY_PROCESSED, show_alert=True
            )


@router.callback_query(MatchAction.filter(F.action == "reject"))
async def handle_match_reject(
    callback: CallbackQuery, callback_data: MatchAction
) -> None:
    match_id = UUID(callback_data.match_id)

    async for session in get_db():
        from ..models import Match

        result = await session.execute(
            select(Match).where(col(Match.id) == match_id)
        )
        match = result.scalar_one_or_none()
        if not match:
            await callback.answer(L.matching.errors.NOT_FOUND, show_alert=True)
            return

        match.status = "rejected"
        await session.commit()
        await callback.answer(L.matching.REJECT_NOTED)


@router.callback_query(ResetAction.filter(F.action == "confirm"))
async def handle_reset_confirm(
    callback: CallbackQuery, callback_data: ResetAction
) -> None:
    """Handler for reset confirmation button"""
    telegram_id = callback_data.telegram_id

    # Authorization check
    if callback.from_user.id != telegram_id:
        await callback.answer(L.system.errors.UNAUTHORIZED, show_alert=True)
        return

    # Validate callback.message is accessible
    message = await validate_callback_message(callback)
    if message is None:
        return

    async for session in get_db():
        # Get or create user and conversation (defensive programming)
        user = await get_or_create_user(telegram_id, session)
        conversation = await get_or_create_conversation(telegram_id, session)

        # Use ProfileService to reset
        profiler = ProfileService(session)
        await profiler.reset_profile(user, conversation)

        # Send playful amnesia message
        await message.edit_text(L.commands.reset.SUCCESS)

        # Send standard greeting (same as /start)
        if conversation:
            await message.answer(L.commands.start.GREETING)
            # Start with empty conversation history (greeting is in system prompt)
            conversation.messages = []
            # Cancel any pending generations for this conversation
            pending_gens = (
                (
                    await session.execute(
                        select(Generation)
                        .where(
                            col(Generation.conversation_id) == conversation.id
                        )
                        .where(col(Generation.status) == "pending")
                    )
                )
                .scalars()
                .all()
            )
            for gen in pending_gens:
                gen.status = "failed"
            await session.commit()
            logger.info(
                "Reset conversation for user %d: empty history",
                telegram_id,
            )

        await callback.answer()


@router.callback_query(ResetAction.filter(F.action == "cancel"))
async def handle_reset_cancel(
    callback: CallbackQuery, callback_data: ResetAction
) -> None:
    """Handler for reset cancellation button"""
    telegram_id = callback_data.telegram_id

    # Authorization check
    if callback.from_user.id != telegram_id:
        await callback.answer(L.system.errors.UNAUTHORIZED, show_alert=True)
        return

    # Validate callback.message is accessible
    message = await validate_callback_message(callback)
    if message is None:
        return

    await message.edit_text(L.commands.reset.CANCELLED)
    await callback.answer()
