"""
Database Configuration

PostgreSQL connection pool. Использует config.get_config().database_url.
"""

from typing import Optional

import asyncpg

from config import get_config

logger = None


def _get_logger():
    """Lazy import logger to avoid circular imports."""
    global logger
    if logger is None:
        import logging

        logger = logging.getLogger(__name__)
    return logger


def get_database_url() -> str:
    """
    PostgreSQL connection URL из config.

    Raises:
        ValueError: Если DATABASE_URL не задан
    """
    url = get_config().database_url
    if not url:
        raise ValueError(
            "DATABASE_URL не задан в .env. "
            "Формат: postgresql://user:password@host:port/database"
        )
    return url


async def create_connection_pool(
    database_url: Optional[str] = None,
    min_size: int = 2,
    max_size: int = 10,
) -> asyncpg.Pool:
    """
    Create a connection pool for PostgreSQL.

    Args:
        database_url: Database connection URL (if None, will load from env)
        min_size: Minimum number of connections in the pool
        max_size: Maximum number of connections in the pool

    Returns:
        AsyncPG connection pool

    Raises:
        ValueError: If database URL is not set
        asyncpg.exceptions.PostgresError: If connection fails
    """
    logger = _get_logger()
    database_url = database_url or get_database_url()

    try:
        pool = await asyncpg.create_pool(
            database_url,
            min_size=min_size,
            max_size=max_size,
            command_timeout=60,
        )
        logger.info(
            f"Created database connection pool (min={min_size}, max={max_size})"
        )
        return pool
    except Exception as e:
        logger.error(f"Failed to create database connection pool: {e}")
        raise
