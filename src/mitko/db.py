"""Plain model lookup helpers — thin wrappers around common SELECT queries."""

from typing import TypeVar
from uuid import UUID

from sqlalchemy import Result, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from .models import Chat, Match, User


async def _select_chat(
    session: AsyncSession, telegram_id: int
) -> Result[tuple[Chat]]:
    return await session.execute(
        select(Chat).where(col(Chat.telegram_id) == telegram_id)
    )


async def get_chat_or_none(
    session: AsyncSession, telegram_id: int
) -> Chat | None:
    return (await _select_chat(session, telegram_id)).scalar_one_or_none()


async def get_chat(session: AsyncSession, telegram_id: int) -> Chat:
    return (await _select_chat(session, telegram_id)).scalar_one()


TModel = TypeVar("TModel", Chat, User)


async def _create(session: AsyncSession, instance: TModel) -> TModel:
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return instance


async def get_or_create_chat(session: AsyncSession, telegram_id: int) -> Chat:
    return await get_chat_or_none(session, telegram_id) or await _create(
        session, Chat(telegram_id=telegram_id, message_history=[])
    )


async def _select_user(
    session: AsyncSession, telegram_id: int
) -> Result[tuple[User]]:
    return await session.execute(
        select(User).where(col(User.telegram_id) == telegram_id)
    )


async def get_user_or_none(
    session: AsyncSession, telegram_id: int
) -> User | None:
    return (await _select_user(session, telegram_id)).scalar_one_or_none()


async def get_user(session: AsyncSession, telegram_id: int) -> User:
    return (await _select_user(session, telegram_id)).scalar_one()


async def get_or_create_user(session: AsyncSession, telegram_id: int) -> User:
    return await get_user_or_none(session, telegram_id) or await _create(
        session, User(telegram_id=telegram_id, state="onboarding")
    )


async def get_match_or_none(
    session: AsyncSession, match_id: UUID
) -> Match | None:
    return (
        await session.execute(select(Match).where(col(Match.id) == match_id))
    ).scalar_one_or_none()
