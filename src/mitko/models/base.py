from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel

# Use get_settings() instead of SETTINGS to avoid importing settings_instance.py.
# That module has module-level SETTINGS initialization which would fail during build.
from ..config import get_settings

# SQLModel.metadata replaces Base.metadata
# Models now inherit from SQLModel directly

engine = create_async_engine(get_settings().database_url, echo=False)
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def init_db():
    """Create all tables - useful for testing or first-time setup"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
