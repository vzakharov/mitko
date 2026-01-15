"""Generation processor for scheduled LLM response generation.

This module implements a sequential queue system for LLM generation:
- Generations are scheduled with a scheduled_for timestamp
- The processor awaits the earliest pending scheduled_for, generates a response, then repeats
- Only one generation happens at a time (sequential, not parallel)
"""

import asyncio
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime

from aiogram import Bot
from genai_prices import calc_price
from pydantic import HttpUrl
from pydantic_ai.models.openai import (
    OpenAIChatModelSettings,
    OpenAIResponsesModelSettings,
)
from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from ..agents.config import LANGUAGE_MODEL
from ..agents.conversation_agent import (
    CONVERSATION_AGENT,
    CONVERSATION_AGENT_INSTRUCTIONS,
)
from ..config import SETTINGS
from ..i18n import L
from ..models import Conversation, Generation, User, async_session_maker
from ..services.profiler import ProfileService
from ..types.messages import HistoryMessage, ProfileData

logger = logging.getLogger(__name__)

# Module-level state
_nudge_event: asyncio.Event | None = None
_processor_task: asyncio.Task[None] | None = None

MESSAGE_HISTORY_MAX_LENGTH = 20


def _get_nudge_event() -> asyncio.Event:
    """Get or create the nudge event (lazy initialization)."""
    global _nudge_event
    if _nudge_event is None:
        _nudge_event = asyncio.Event()
    return _nudge_event


def nudge_processor() -> None:
    """Signal the processor that new work may be available."""
    event = _get_nudge_event()
    event.set()


async def _find_next_ripe_generation(
    session: AsyncSession,
) -> Generation | None:
    """Find the pending generation with earliest scheduled_for <= now."""
    now = datetime.now(UTC)
    result = await session.execute(
        select(Generation)
        .where(col(Generation.status) == "pending")
        .where(col(Generation.scheduled_for) <= now)
        .order_by(col(Generation.scheduled_for).asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_next_scheduled_time(session: AsyncSession) -> datetime | None:
    """Get the earliest pending scheduled_for time (for wait calculation)."""
    result = await session.execute(
        select(sql_func.min(Generation.scheduled_for)).where(
            col(Generation.status) == "pending"
        )
    )
    return result.scalar_one_or_none()


def _format_history_for_instructions(
    history: list[HistoryMessage],
) -> str | None:
    """Format history as readable text for instructions injection.

    Includes truncation for very long conversations to avoid token overflow.
    TODO: implement summarization for longer histories.
    """
    if not history:
        return None

    # Truncate to last MESSAGE_HISTORY_MAX_LENGTH messages to avoid excessive token usage
    truncated_history = history[-MESSAGE_HISTORY_MAX_LENGTH:]
    truncation_notice = ""
    if len(history) > MESSAGE_HISTORY_MAX_LENGTH:
        truncation_notice = f"[Earlier messages truncated - showing last {MESSAGE_HISTORY_MAX_LENGTH} of {len(history)} messages]\n\n"

    formatted_messages = list[str]()
    for msg in truncated_history:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        formatted_messages.append(f"{role_label}: {msg['content']}")

    return f"Previous conversation history:\n{truncation_notice}{chr(10).join(formatted_messages)}"


def _is_expired_response_error(error: Exception) -> bool:
    """Check if error indicates expired/missing Responses API response.

    Be conservative: only match specific known patterns from OpenAI.
    """
    from pydantic_ai.exceptions import ModelHTTPError

    if not isinstance(error, ModelHTTPError):
        return False

    error_message = str(error).lower()

    # Known patterns from OpenAI Responses API:
    # - "Container is expired" (HTTP 400)
    # - "not found" (HTTP 404)
    is_expired = (
        "container is expired" in error_message or "not found" in error_message
    )

    return is_expired


def _format_profile_card(profile: ProfileData) -> str:
    """Format profile as a user-visible card."""
    card_parts = [L.profile.CARD_HEADER + "\n"]

    # Role
    roles = list[str]()
    if profile.is_seeker:
        roles.append(L.profile.ROLE_SEEKER)
    if profile.is_provider:
        roles.append(L.profile.ROLE_PROVIDER)
    card_parts.append(
        f"{L.profile.ROLE_LABEL}: {L.profile.ROLE_SEPARATOR.join(roles)}"
    )

    # Summary
    card_parts.append(f"\n\n{profile.summary}")

    return "".join(card_parts)


async def _process_generation(
    bot: Bot, generation: Generation, session: AsyncSession
) -> None:
    """Process a single generation: generate response and send it."""
    # Fetch conversation
    conv_result = await session.execute(
        select(Conversation).where(
            col(Conversation.id) == generation.conversation_id
        )
    )
    logger.info(
        "Processing generation %s for conversation %s",
        generation.id,
        generation.conversation_id,
    )
    conv = conv_result.scalar_one_or_none()
    if conv is None:
        logger.error(
            "Conversation %s not found for generation %s",
            generation.conversation_id,
            generation.id,
        )
        return

    # Get user for profile operations
    result = await session.execute(
        select(User).where(col(User.telegram_id) == conv.telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        logger.error(
            "User %d not found for conversation %s", conv.telegram_id, conv.id
        )
        return

    # Consume user_prompt
    if not conv.user_prompt:
        logger.error(
            "Generation %s has no user_prompt for conversation %s",
            generation.id,
            conv.id,
        )
        return

    user_prompt = conv.user_prompt
    conv.user_prompt = None  # Clear immediately
    await session.commit()

    instructions_with_history = "\n\n".join(
        [
            piece
            for piece in [
                CONVERSATION_AGENT_INSTRUCTIONS,
                _format_history_for_instructions(conv.message_history),
            ]
            if piece
        ]
    )

    if SETTINGS.use_openai_responses_api:
        model_settings = OpenAIResponsesModelSettings(
            openai_prompt_cache_retention="24h",
        )

        if conv.last_responses_api_response_id:
            model_settings["openai_previous_response_id"] = (
                conv.last_responses_api_response_id
            )
            try:
                result = await CONVERSATION_AGENT.run(
                    user_prompt,
                    model_settings=model_settings,
                )
            except Exception as e:
                if _is_expired_response_error(e):
                    logger.warning(
                        "Responses API state expired for conversation %s (response_id=%s): %s. Falling back to history injection.",
                        conv.id,
                        conv.last_responses_api_response_id,
                        str(e),
                    )

                    conv.last_responses_api_response_id = None
                    await session.commit()

                    model_settings.pop("openai_previous_response_id", None)
                    result = await CONVERSATION_AGENT.run(
                        user_prompt,
                        model_settings=model_settings,
                        instructions=instructions_with_history,
                    )
                else:
                    raise
        else:
            result = await CONVERSATION_AGENT.run(
                user_prompt,
                model_settings=model_settings,
                instructions=instructions_with_history,
            )
    else:
        result = await CONVERSATION_AGENT.run(
            user_prompt,
            model_settings=(
                OpenAIChatModelSettings(
                    # openai_prompt_cache_retention="24h", # not supported for non-Responses API for our models of interest
                    openai_prompt_cache_key=str(conv.id),
                )
                if SETTINGS.llm_provider == "openai"
                else None
            ),
            instructions=instructions_with_history,
        )

    response = result.output

    # Handle profile creation/update
    if response.profile:
        profiler = ProfileService(session)
        is_update = user.is_complete
        await profiler.create_or_update_profile(
            user, response.profile, is_update=is_update
        )

        # Prepare response text
        profile_card = _format_profile_card(response.profile)
        response_text = f"{response.utterance}\n\n{profile_card}"
    else:
        response_text = response.utterance

    # Re-fetch conversation to check if new messages arrived
    await session.refresh(conv)
    new_messages_arrived = conv.user_prompt is not None

    logger.info(
        "Completion phase: new_messages=%s",
        new_messages_arrived,
    )

    # Handle placeholder message and send response
    if generation.placeholder_message_id:
        if new_messages_arrived:
            # Edit placeholder message with final response
            try:
                await bot.edit_message_text(
                    text=response_text,
                    chat_id=conv.telegram_id,
                    message_id=generation.placeholder_message_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to edit placeholder message %d: %s, sending as new message",
                    generation.placeholder_message_id,
                    e,
                )
                # Fallback: send as new message
                await bot.send_message(conv.telegram_id, response_text)
        else:
            # Delete placeholder message and send response as new message (user gets notification)
            try:
                await bot.delete_message(
                    chat_id=conv.telegram_id,
                    message_id=generation.placeholder_message_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to delete placeholder message %d: %s",
                    generation.placeholder_message_id,
                    e,
                )

            # Send final response as new message
            await bot.send_message(conv.telegram_id, response_text)
    else:
        # No placeholder message (old generation) - just send response
        await bot.send_message(conv.telegram_id, response_text)

    # Update conversation history for fallback
    conv.message_history = [
        *conv.message_history,
        {"role": "user", "content": user_prompt},
        {
            "role": "assistant",
            "content": json.dumps(response.model_dump(), ensure_ascii=False),
        },
    ]

    usage = result.usage()
    generation.cached_input_tokens = usage.cache_read_tokens
    generation.uncached_input_tokens = (
        usage.input_tokens - usage.cache_read_tokens
    )
    generation.output_tokens = usage.output_tokens

    # Calculate cost using genai-prices
    try:
        price_data = calc_price(
            usage,
            model_ref=LANGUAGE_MODEL.model_name,
            provider_id=SETTINGS.llm_provider,
        )
        generation.cost_usd = float(price_data.total_price)

        logger.info(
            "Calculated cost for generation %s: $%.6f (%d cached + %d uncached input, %d output tokens)",
            generation.id,
            generation.cost_usd,
            generation.cached_input_tokens or 0,
            generation.uncached_input_tokens or 0,
            generation.output_tokens or 0,
        )
    except Exception as e:
        # Fail gracefully - cost calculation should not break generation processing
        logger.warning(
            "Failed to calculate cost for generation %s: %s",
            generation.id,
            str(e),
            exc_info=True,
        )
        generation.cost_usd = None

    if response_id := result.response.provider_response_id:
        generation.provider_response_id = response_id
        if SETTINGS.llm_provider == "openai":
            generation.log_url = HttpUrl(
                f"https://platform.openai.com/logs/{response_id}"
            )
        if SETTINGS.use_openai_responses_api:
            conv.last_responses_api_response_id = response_id

    await session.commit()

    logger.info(
        "Processed generation %s: message history updated",
        generation.id,
    )


async def _processor_loop(bot: Bot) -> None:
    """Main processor loop - runs indefinitely, processing one generation at a time."""
    event = _get_nudge_event()

    while True:
        try:
            async with async_session_maker() as session:
                # Find next ripe generation
                generation = await _find_next_ripe_generation(session)

                if generation is not None:
                    # Fetch conversation for error handling
                    conv_result = await session.execute(
                        select(Conversation).where(
                            col(Conversation.id) == generation.conversation_id
                        )
                    )
                    conv = conv_result.scalar_one_or_none()
                    telegram_id = conv.telegram_id if conv else None

                    # Mark as started and transfer status message
                    generation.status = "started"
                    generation.started_at = datetime.now(UTC)

                    # Transfer status message from conversation to generation
                    if conv and conv.status_message_id:
                        generation.placeholder_message_id = (
                            conv.status_message_id
                        )
                        conv.status_message_id = None

                    await session.commit()

                    # Update placeholder message to thinking emoji and send typing indicator
                    if generation.placeholder_message_id and telegram_id:
                        try:
                            await bot.edit_message_text(
                                text=L.system.THINKING,
                                chat_id=telegram_id,
                                message_id=generation.placeholder_message_id,
                            )
                        except Exception as e:
                            logger.warning(
                                "Failed to edit placeholder message %d: %s",
                                generation.placeholder_message_id,
                                e,
                            )

                        # TODO: Consider periodic refresh every 4s to keep typing indicator alive
                        try:
                            await bot.send_chat_action(
                                chat_id=telegram_id, action="typing"
                            )
                        except Exception as e:
                            logger.warning(
                                "Failed to send typing indicator: %s", e
                            )

                        logger.info(
                            "Processing started, placeholder_msg_id=%s",
                            generation.placeholder_message_id,
                        )

                    # Process the generation
                    try:
                        await _process_generation(bot, generation, session)
                        generation.status = "completed"
                        await session.commit()
                    except Exception as e:
                        logger.exception(
                            "Error processing generation %s: %s",
                            generation.id,
                            e,
                        )
                        # Mark as failed and notify user
                        generation.status = "failed"
                        await session.commit()
                        if telegram_id is not None:
                            await bot.send_message(
                                telegram_id,
                                L.system.errors.GENERATION_FAILED,
                            )

                    # Immediately check for more work (no wait)
                    continue

                # No ripe generation - calculate wait time
                next_time = await _get_next_scheduled_time(session)

            # Wait logic (outside session context)
            if next_time is not None:
                now = datetime.now(UTC)
                wait_seconds = (next_time - now).total_seconds()
                if wait_seconds > 0:
                    event.clear()
                    with suppress(TimeoutError):
                        await asyncio.wait_for(
                            event.wait(), timeout=wait_seconds
                        )
            else:
                # No pending generations - wait indefinitely for nudge
                event.clear()
                await event.wait()

        except Exception as e:
            logger.exception("Unexpected error in processor loop: %s", e)
            # Brief pause before retrying to avoid tight error loops
            await asyncio.sleep(1.0)


def start_generation_processor(bot: Bot) -> None:
    """Start the generation processor as a background task."""
    global _processor_task
    if _processor_task is not None:
        logger.warning("Generation processor already running")
        return

    _processor_task = asyncio.create_task(_processor_loop(bot))
    logger.info("Started generation processor")


async def stop_generation_processor() -> None:
    """Stop the generation processor gracefully."""
    global _processor_task, _nudge_event

    if _processor_task is not None:
        _processor_task.cancel()
        with suppress(asyncio.CancelledError):
            await _processor_task
        _processor_task = None
        logger.info("Stopped generation processor")

    _nudge_event = None
