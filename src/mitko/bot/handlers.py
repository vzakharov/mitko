import asyncio
import logging
import uuid
from datetime import UTC, datetime
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InaccessibleMessage, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..i18n import L
from ..jobs.generation_processor import nudge_processor
from ..models import Conversation, Generation, User, get_db
from ..services.generation_orchestrator import GenerationOrchestrator
from ..services.profiler import ProfileService
from .keyboards import MatchAction, ResetAction, reset_confirmation_keyboard

router = Router()
logger = logging.getLogger(__name__)

# Delay before nudging processor to allow rapid successive messages to be processed
# (e.g., long messages split by Telegram into multiple parts)
NUDGE_DELAY_SECONDS = 1.0

_bot_instance: Bot | None = None


def reset_conversation_state(conversation: Conversation) -> None:
    """Reset conversation to empty state, clearing all history and Responses API state."""
    conversation.message_history = []
    conversation.user_prompt = None
    conversation.last_responses_api_response_id = None


def set_bot_instance(bot: Bot) -> None:
    global _bot_instance
    _bot_instance = bot


def get_bot() -> Bot:
    if _bot_instance is None:
        raise RuntimeError("Bot instance not set")
    return _bot_instance


def _format_profile_for_display(user: User) -> str:
    """Combine matching_summary + practical_context for display"""
    parts = [user.matching_summary or ""]
    if user.practical_context:
        parts.append(user.practical_context)
    return "\n\n".join(parts)


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
        conv = Conversation(telegram_id=telegram_id, message_history=[])
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
            user.matching_summary is not None
            or user.is_seeker is not None
            or user.is_provider is not None
            or conv.message_history != []
            or conv.user_prompt is not None
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
            reset_conversation_state(conv)
            await session.commit()
            logger.info(
                "Started conversation for user %d: empty history",
                message.from_user.id,
            )


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


async def _has_started_generation(
    conversation_id: uuid.UUID, session: AsyncSession
) -> bool:
    """Check if conversation has a generation that has started processing."""
    result = await session.execute(
        select(Generation)
        .where(col(Generation.conversation_id) == conversation_id)
        .where(col(Generation.status) == "started")
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _format_time_delta(scheduled_for: datetime) -> str:
    """Format time delta with rounding and i18n support."""
    now = datetime.now(UTC)
    delta = scheduled_for - now
    total_seconds = delta.total_seconds()

    # Past or very soon
    if total_seconds <= 0:
        return L.system.SCHEDULED_REPLY_SOON

    # Less than 1 minute
    if total_seconds < 60:
        return L.system.SCHEDULED_REPLY_SHORTLY

    # Format with hours and minutes
    total_minutes = int(total_seconds / 60)
    # Round up to nearest 5
    total_minutes = ((total_minutes + 4) // 5) * 5

    hours = total_minutes // 60
    minutes = total_minutes % 60

    # Build duration string
    parts = list[str]()
    if hours > 0:
        parts.append(f"{hours} {L.system.TIME_UNIT_HOUR}")
    if minutes > 0:
        parts.append(f"{minutes} {L.system.TIME_UNIT_MINUTE}")

    duration = " ".join(parts)
    return L.system.SCHEDULED_REPLY_IN.format(duration=duration)


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

        # Set or append to user_prompt
        if conv.user_prompt:
            conv.user_prompt += "\n\n" + message.text
        else:
            conv.user_prompt = message.text

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
            # Re-send status message if exists and no generation started yet
            if conv.status_message_id and not await _has_started_generation(
                conv.id, session
            ):
                bot = get_bot()
                # Delete old status message
                try:
                    await bot.delete_message(
                        chat_id=conv.telegram_id,
                        message_id=conv.status_message_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to delete old status message %d: %s",
                        conv.status_message_id,
                        e,
                    )

                # Get earliest pending generation for timeline calculation
                result = await session.execute(
                    select(Generation)
                    .where(col(Generation.conversation_id) == conv.id)
                    .where(col(Generation.status) == "pending")
                    .order_by(col(Generation.scheduled_for).asc())
                    .limit(1)
                )
                pending_gen = result.scalar_one()

                # Send new status message with updated timeline
                status_text = _format_time_delta(pending_gen.scheduled_for)
                status_msg = await message.answer(status_text)
                conv.status_message_id = status_msg.message_id

                logger.info(
                    "Re-sent status message: new_msg_id=%d, scheduled_for=%s",
                    status_msg.message_id,
                    pending_gen.scheduled_for,
                )

            # Message stored in user_prompt, will be processed by pending generation
            await session.commit()
            logger.info(
                "Stored user message for %d in user_prompt (pending generation exists)",
                message.from_user.id,
            )
        else:
            # Create a new generation
            generation_service = GenerationOrchestrator(session)
            generation = await generation_service.create_generation(
                conversation_id=conv.id
            )
            nudge_processor()

            # Send acknowledgment with estimated reply time
            status_text = _format_time_delta(generation.scheduled_for)
            status_msg = await message.answer(status_text)

            # Store status message ID in conversation (not generation)
            conv.status_message_id = status_msg.message_id
            await session.commit()

            logger.info(
                "Status message sent: msg_id=%d, scheduled_for=%s",
                status_msg.message_id,
                generation.scheduled_for,
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
            profile_display_a = _format_profile_for_display(user_b)
            profile_display_b = _format_profile_for_display(user_a)
            await bot.send_message(
                user_a.telegram_id,
                L.matching.CONNECTION_MADE.format(profile=profile_display_a),
            )
            await bot.send_message(
                user_b.telegram_id,
                L.matching.CONNECTION_MADE.format(profile=profile_display_b),
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
            reset_conversation_state(conversation)
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
