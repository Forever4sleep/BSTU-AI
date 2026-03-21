"""Async SQLAlchemy engine and session factory."""

import logging

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import get_config
from services.ingestion_service.db.models import Base

logger = logging.getLogger(__name__)


def create_db_engine(url: str | None = None) -> AsyncEngine:
    db_url = url or get_config().ingestion_db_url
    if not db_url:
        raise ValueError("INGESTION_DB_URL is not set in .env")
    return create_async_engine(db_url, echo=False, pool_size=5, max_overflow=10)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")
