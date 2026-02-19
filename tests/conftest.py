"""Pytest fixtures for testing."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlmodel import SQLModel


@pytest.fixture(scope="session")
def event_loop():
    """Create session-scoped event loop for async database sharing."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create in-memory SQLite database engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture(scope="session")
async def db_connection(
    db_engine: AsyncEngine,
) -> AsyncGenerator[AsyncConnection, None]:
    """Session-scoped connection shared across all tests."""
    async with db_engine.connect() as connection:
        yield connection


@pytest.fixture
async def db_session(
    db_connection: AsyncConnection,
) -> AsyncGenerator[AsyncSession, None]:
    """Function-scoped session with nested transaction for isolation.

    Uses a savepoint (BEGIN SAVEPOINT) so that even code calling
    session.commit() is rolled back after the test.
    """
    transaction = await db_connection.begin_nested()
    session = AsyncSession(bind=db_connection, expire_on_commit=False)

    yield session

    await session.close()
    await transaction.rollback()
