"""Plain model lookup helpers — thin wrappers around common SELECT queries."""

from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import Result, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from .models import (
    Announce,
    AnnounceStatus,
    Chat,
    Match,
    User,
    UserGroup,
    UserGroupMember,
)


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


TModel = TypeVar("TModel", Announce, Chat, User, UserGroup, UserGroupMember)


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


async def filter_users(
    session: AsyncSession, filters: dict[str, Any]
) -> list[User]:
    # TODO: support array-contains filtering (e.g. {"flags": ["test"]}
    #       meaning User.flags must contain all these values)
    query = select(User)
    for key, value in filters.items():
        query = query.where(col(getattr(User, key)) == value)
    return list((await session.execute(query)).scalars().all())


async def create_user_group(
    session: AsyncSession,
    users: list[User],
    name: str | None = None,
) -> UserGroup:
    group = UserGroup(name=name)
    session.add(group)
    await session.flush()
    for user in users:
        session.add(
            UserGroupMember(group_id=group.id, user_id=user.telegram_id)
        )
    await session.commit()
    await session.refresh(group)
    return group


async def create_announce(
    session: AsyncSession,
    group: UserGroup,
    thread_id: int,
    text: str,
) -> Announce:
    return await _create(
        session,
        Announce(group_id=group.id, thread_id=thread_id, text=text),
    )


async def get_announce_or_none(
    session: AsyncSession, thread_id: int
) -> Announce | None:
    if announce := (
        await session.execute(
            select(Announce).where(col(Announce.thread_id) == thread_id)
        )
    ).scalar_one_or_none():
        await session.refresh(announce, ["group"])
        await session.refresh(announce.group, ["members"])
        for member in announce.group.members:
            await session.refresh(member, ["user"])
        return announce


async def update_announce_status(
    session: AsyncSession, announce: Announce, status: AnnounceStatus
) -> None:
    announce.status = status
    await session.commit()
