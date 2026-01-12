import logging
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
from ..models import Conversation, User, get_db
from ..services.profiler import ProfileService
from ..types import AssistantMessage, UserMessage
from ..types.messages import ConversationResponse
from .keyboards import MatchAction, ResetAction, reset_confirmation_keyboard

router = Router()
logger = logging.getLogger(__name__)

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
            # New user - just send greeting and initialize
            await message.answer(L.commands.start.GREETING)
            # Replace conversation history with greeting to start fresh
            conv.messages = [
                AssistantMessage.create(
                    ConversationResponse(
                        utterance=L.commands.start.GREETING, profile=None
                    )
                )
            ]
            await session.commit()
            last_msg = conv.messages[-1] if conv.messages else None
            last_text = (
                last_msg.content.utterance[:50]
                if isinstance(last_msg, AssistantMessage)
                else "none"
            )
            logger.info(
                "Started conversation for user %d: %d messages, last: %s",
                message.from_user.id,
                len(conv.messages),
                last_text,
            )


async def _get_max_scheduled_time(session: AsyncSession) -> datetime | None:
    """Get the maximum scheduled_for time across all conversations."""
    result = await session.execute(
        select(sql_func.max(Conversation.scheduled_for))
    )
    return result.scalar_one_or_none()


@router.message()
async def handle_message(message: Message) -> None:
    if not message.text or message.from_user is None:
        return

    async for session in get_db():
        await get_or_create_user(message.from_user.id, session)
        conv = await get_or_create_conversation(message.from_user.id, session)

        # Add user message
        conv.messages.append(UserMessage.create(message.text))

        # Schedule generation if not already scheduled
        if conv.scheduled_for is None:
            now = datetime.now(UTC)
            interval = timedelta(seconds=settings.generation_interval_seconds)

            # Find max scheduled time to maintain queue order
            max_scheduled = await _get_max_scheduled_time(session)

            if max_scheduled is not None and max_scheduled > now:
                # Queue after the last scheduled conversation
                conv.scheduled_for = max_scheduled + interval
            else:
                # No queue or all in past - schedule for now + interval
                conv.scheduled_for = now + interval

        await session.commit()

        # Send acknowledgment with estimated reply time
        # TODO: Better UX - link to explanation, handle near-instant cases differently
        reply_time = conv.scheduled_for.strftime("%H:%M:%S")
        await message.answer(L.system.SCHEDULED_REPLY.format(time=reply_time))

        logger.debug(
            "Stored user message for %d: %d total messages, scheduled_for=%s",
            message.from_user.id,
            len(conv.messages),
            conv.scheduled_for,
        )

        # Nudge the processor (fire-and-forget)
        nudge_processor()


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
            # Replace conversation history with greeting to start fresh
            conversation.messages = [
                AssistantMessage.create(
                    ConversationResponse(
                        utterance=L.commands.start.GREETING, profile=None
                    )
                )
            ]
            # Cancel any pending generation
            conversation.scheduled_for = None
            await session.commit()
            last_msg = (
                conversation.messages[-1] if conversation.messages else None
            )
            last_text = (
                last_msg.content.utterance[:50]
                if isinstance(last_msg, AssistantMessage)
                else "none"
            )
            logger.info(
                "Reset conversation for user %d: %d messages, last: %s",
                telegram_id,
                len(conversation.messages),
                last_text,
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
