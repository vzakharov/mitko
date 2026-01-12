from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from ..config import settings

# SQLModel.metadata replaces Base.metadata
# Models now inherit from SQLModel directly

engine = create_async_engine(settings.database_url, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def init_db():
    """Create all tables - useful for testing or first-time setup"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
