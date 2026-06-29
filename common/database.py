"""Async SQLAlchemy engine for the experiment database."""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from common.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def create_tables() -> None:
    """Create all experiment tables (idempotent)."""
    async with engine.begin() as conn:
        # Importing here so Base is fully populated before create_all
        from common.models import ExperimentSubmission  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
