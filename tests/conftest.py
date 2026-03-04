"""Pytest fixtures for testing."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlmodel import SQLModel

# Import all models to register them with SQLModel.metadata
from mitko.models import (  # noqa: F401
    Announcement,
    Chat,
    Generation,
    Match,
    User,
)

# Prevent unused-imports errors from static checkers by referencing the imported
# models in a no-op assignment.
_ = (Announcement, Chat, Generation, Match, User)

_engine: AsyncEngine | None = None
_connection: AsyncConnection | None = None


async def _init_db() -> tuple[AsyncEngine, AsyncConnection]:
    """Initialize the database engine and connection."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(_register_sqlite_functions)
        await conn.run_sync(SQLModel.metadata.create_all)

    connection = await engine.connect()
    return engine, connection


def _register_sqlite_functions(connection: Connection) -> None:
    """Register custom SQLite functions for PostgreSQL compatibility."""
    aiosqlite_conn = connection.connection.driver_connection
    assert aiosqlite_conn is not None
    sqlite3_conn = aiosqlite_conn._conn

    sqlite3_conn.create_function("greatest", -1, lambda *args: max(args))  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    sqlite3_conn.create_function("least", -1, lambda *args: min(args))  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]


def pytest_configure(config: Any) -> None:
    """Initialize the test database at pytest startup."""
    global _engine, _connection
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _engine, _connection = loop.run_until_complete(_init_db())


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Clean up the database after all tests."""
    if _connection or _engine:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        if _connection:
            loop.run_until_complete(_connection.close())
        if _engine:
            loop.run_until_complete(_engine.dispose())


@pytest.fixture(scope="session")
def db_engine() -> AsyncEngine:
    """Provide the test database engine."""
    assert _engine is not None
    return _engine


@pytest.fixture(scope="session")
def db_connection() -> AsyncConnection:
    """Provide the database connection for tests."""
    assert _connection is not None
    return _connection


@pytest_asyncio.fixture
async def db_session(
    db_connection: AsyncConnection,
) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with transaction isolation."""
    transaction = await db_connection.begin_nested()
    session = AsyncSession(bind=db_connection, expire_on_commit=False)

    yield session

    await session.close()
    await transaction.rollback()
