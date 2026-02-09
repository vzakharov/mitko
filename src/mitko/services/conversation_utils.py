"""Utilities for conversation message handling."""

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from src.mitko.models.conversation import Conversation

INJECTED_MESSAGE_PREFIX = "[Admin-injected message - not LLM-generated - stored for memory continuity]"


async def send_and_record_bot_message(
    conversation: Conversation,
    message_text: str,
    bot: Bot,
    session: AsyncSession,
    prefix: str = INJECTED_MESSAGE_PREFIX,
) -> None:
    """
    Send a bot-initiated message to the user and record it in conversation history.

    This is used for bot-initiated messages (not LLM-generated responses):
    - Profile update prompts when profiler version changes
    - Announcements or notifications
    - Any message where the bot needs to "remember" what it said

    The message is stored with a prefix to distinguish it from LLM responses.
    Invalidates OpenAI Responses API state to force history injection on next turn.

    Args:
        conversation: Conversation object with telegram_id and message_history
        message_text: The text to send (plain text, formatted with markdown)
        bot: Telegram Bot instance
        session: DB session for committing history
    """
    conversation.message_history = [
        *conversation.message_history,
        {"role": "assistant", "content": f"{prefix} {message_text}"},
    ]

    conversation.last_responses_api_response_id = None

    session.add(conversation)
    await bot.send_message(conversation.telegram_id, message_text)
    await session.commit()
