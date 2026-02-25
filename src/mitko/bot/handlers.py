import asyncio
import logging
import uuid
from datetime import UTC, datetime
from uuid import UUID

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..config import SETTINGS
from ..db import (
    get_match_or_none,
    get_or_create_chat,
    get_or_create_user,
    get_user,
)
from ..i18n import L
from ..jobs.generation_processor import nudge_processor
from ..models import Chat, Generation, User, get_db
from ..services.chat_utils import send_and_record_bot_message
from ..services.generation_orchestrator import GenerationOrchestrator
from ..services.profiler import ProfileService
from .activation import register_activation_handlers
from .bot_instance import get_bot
from .keyboards import (
    IntroAction,
    MatchAction,
    ResetAction,
    intro_keyboard,
    reset_confirmation_keyboard,
)
from .utils import get_callback_message

router = Router()
logger = logging.getLogger(__name__)

router.message.filter(F.chat.id != SETTINGS.admin_group_id)
router.callback_query.filter(F.message.chat.id != SETTINGS.admin_group_id)

register_activation_handlers(router)

# Delay before nudging processor to allow rapid successive messages to be processed
# (e.g., long messages split by Telegram into multiple parts)
NUDGE_DELAY_SECONDS = 1.0


async def _get_or_create_user_with_sync(
    session: AsyncSession, tg_user: TgUser
) -> User:
    """Get or create user and sync metadata from Telegram (username)."""
    user = await get_or_create_user(session, tg_user.id)
    user.username = tg_user.username
    return user


def _reset_chat_state(chat: Chat) -> None:
    """Reset chat to empty state, clearing all history and Responses API state."""
    chat.message_history = []
    chat.user_prompt = None
    chat.last_responses_api_response_id = None


async def _send_greeting(message: Message) -> None:
    """Send greeting message with "Tell me more" button."""
    await message.answer(
        L.commands.start.GREETING, reply_markup=intro_keyboard()
    )


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    assert message.from_user is not None
    async for session in get_db():
        user = await _get_or_create_user_with_sync(session, message.from_user)
        chat = await get_or_create_chat(session, message.from_user.id)

        # Check if user has ANY existing data
        has_data = (
            user.matching_summary is not None
            or user.is_seeker is not None
            or user.is_provider is not None
            or chat.message_history != []
            or chat.user_prompt is not None
        )

        if has_data:
            # Existing user - show reset warning with confirmation keyboard
            await message.answer(
                L.commands.reset.WARNING,
                reply_markup=reset_confirmation_keyboard(message.from_user.id),
            )
        else:
            # New user - send short greeting with "Tell me more" button
            await _send_greeting(message)
            _reset_chat_state(chat)
            await session.commit()
            logger.info(
                "Started chat for user %d: empty history",
                message.from_user.id,
            )


@router.callback_query(IntroAction.filter(F.action == "tell_me_more"))
async def handle_tell_me_more(callback: CallbackQuery) -> None:
    assert callback.from_user is not None
    async for session in get_db():
        chat = await get_or_create_chat(session, callback.from_user.id)
        await send_and_record_bot_message(
            bot=get_bot(),
            recipient=chat,
            message_text=L.commands.start.TELL_ME_MORE_REPLY,
            session=session,
            prefix=None,
            system_message='User pressed "Tell me more" button, triggering the hardcoded reply below',
            system_before_assistant=True,
        )
        await get_callback_message(callback).edit_reply_markup(
            reply_markup=None
        )
        chat.omit_pitch_in_instructions = True
        await session.commit()
    await callback.answer()


async def _has_pending_generation(
    chat_id: uuid.UUID, session: AsyncSession
) -> bool:
    """Check if chat has a pending ChatGeneration (not MatchIntroGeneration)."""
    result = await session.execute(
        select(Generation)
        .where(col(Generation.chat_id) == chat_id)
        .where(col(Generation.status) == "pending")
        .where(col(Generation.match_id).is_(None))  # Exclude match intros
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _has_started_generation(
    chat_id: uuid.UUID, session: AsyncSession
) -> bool:
    """Check if chat has a generation that has started processing."""
    result = await session.execute(
        select(Generation)
        .where(col(Generation.chat_id) == chat_id)
        .where(col(Generation.status) == "started")
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _format_time_delta(scheduled_for: datetime) -> str:
    """Format time delta with rounding and i18n support."""
    now = datetime.now(UTC)
    # Handle both naive (SQLite) and aware (PostgreSQL) datetimes
    if scheduled_for.tzinfo is None:
        scheduled_for = scheduled_for.replace(tzinfo=UTC)
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
    if not message.text:
        return
    assert message.from_user is not None

    async for session in get_db():
        await _get_or_create_user_with_sync(session, message.from_user)
        chat = await get_or_create_chat(session, message.from_user.id)

        # Set or append to user_prompt
        if chat.user_prompt:
            chat.user_prompt += "\n\n" + message.text
        else:
            chat.user_prompt = message.text

        # Acquire exclusive lock on chat row to prevent race conditions
        # when multiple messages arrive simultaneously (e.g., long messages split by Telegram)
        await session.execute(
            select(Chat).where(col(Chat.id) == chat.id).with_for_update()
        )

        # Check if there's already a pending generation for this chat
        has_pending = await _has_pending_generation(chat.id, session)

        if has_pending:
            # Re-send status message if exists and no generation started yet
            if chat.status_message_id and not await _has_started_generation(
                chat.id, session
            ):
                bot = get_bot()
                # Delete old status message
                try:
                    await bot.delete_message(
                        chat_id=chat.telegram_id,
                        message_id=chat.status_message_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to delete old status message %d: %s",
                        chat.status_message_id,
                        e,
                    )

                # Get earliest pending generation for timeline calculation
                result = await session.execute(
                    select(Generation)
                    .where(col(Generation.chat_id) == chat.id)
                    .where(col(Generation.status) == "pending")
                    .order_by(col(Generation.scheduled_for).asc())
                    .limit(1)
                )
                pending_gen = result.scalar_one()

                # Send new status message with updated timeline
                status_text = _format_time_delta(pending_gen.scheduled_for)
                status_msg = await message.answer(status_text)
                chat.status_message_id = status_msg.message_id

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
                chat_id=chat.id
            )

            # Send acknowledgment with estimated reply time
            status_text = _format_time_delta(generation.scheduled_for)
            status_msg = await message.answer(status_text)

            # Store status message ID in chat (not generation)
            chat.status_message_id = status_msg.message_id
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
        match = await get_match_or_none(session, match_id)
        assert match is not None
        assert match.user_b_id is not None

        user_a = await get_user(session, match.user_a_id)
        user_b = await get_user(session, match.user_b_id)

        if user_a.telegram_id == callback.from_user.id:
            current_user, other_user = user_a, user_b
        else:
            assert user_b.telegram_id == callback.from_user.id
            current_user, other_user = user_b, user_a

        assert match.status in ("qualified", "a_accepted", "b_accepted")

        if match.status == "qualified":
            is_user_a = current_user.telegram_id == user_a.telegram_id
            match.status = "a_accepted" if is_user_a else "b_accepted"
            await session.commit()
            await callback.answer(L.matching.ACCEPT_WAITING)
        elif match.status in ("a_accepted", "b_accepted"):
            match.status = "connected"
            await session.commit()

            await callback.answer("✓")
            await send_and_record_bot_message(
                get_bot(),
                current_user.telegram_id,
                L.matching.CONNECTION_MADE.format(
                    contact=f"[{other_user.username or 'Contact'}](tg://user?id={other_user.telegram_id})"
                ),
                session,
                parse_mode=ParseMode.MARKDOWN,
            )
            await send_and_record_bot_message(
                get_bot(),
                other_user.telegram_id,
                L.matching.CONNECTION_MADE.format(
                    contact=f"[{current_user.username or 'Contact'}](tg://user?id={current_user.telegram_id})"
                ),
                session,
                parse_mode=ParseMode.MARKDOWN,
            )


@router.callback_query(MatchAction.filter(F.action == "reject"))
async def handle_match_reject(
    callback: CallbackQuery, callback_data: MatchAction
) -> None:
    match_id = UUID(callback_data.match_id)

    async for session in get_db():
        match = await get_match_or_none(session, match_id)
        assert match is not None
        match.status = "rejected"
        await session.commit()
        await callback.answer(L.matching.REJECT_NOTED)


@router.callback_query(ResetAction.filter(F.action == "confirm"))
async def handle_reset_confirm(
    callback: CallbackQuery, callback_data: ResetAction
) -> None:
    telegram_id = callback_data.telegram_id
    assert callback.from_user.id == telegram_id
    message = get_callback_message(callback)

    async for session in get_db():
        # Get or create user and chat (defensive programming)
        user = await _get_or_create_user_with_sync(session, callback.from_user)
        chat = await get_or_create_chat(session, telegram_id)

        # Use ProfileService to reset
        profiler = ProfileService(session)
        await profiler.reset_profile(user, chat)

        # Send playful amnesia message
        await message.edit_text(L.commands.reset.SUCCESS)

        # Send standard greeting (same as /start)
        await _send_greeting(message)
        _reset_chat_state(chat)
        # Cancel any pending generations for this chat
        pending_gens = (
            (
                await session.execute(
                    select(Generation)
                    .where(col(Generation.chat_id) == chat.id)
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
            "Reset chat for user %d: empty history",
            telegram_id,
        )

        await callback.answer()


@router.callback_query(ResetAction.filter(F.action == "cancel"))
async def handle_reset_cancel(
    callback: CallbackQuery, callback_data: ResetAction
) -> None:
    assert callback.from_user.id == callback_data.telegram_id

    await get_callback_message(callback).edit_text(L.commands.reset.CANCELLED)
    await callback.answer()
