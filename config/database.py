"""
Database Configuration

Handles PostgreSQL database connection configuration and setup.
"""

import os
from typing import Optional

import asyncpg
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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
    Get PostgreSQL database connection URL from environment variable.

    Format: postgresql://user:password@host:port/database

    Returns:
        Database connection URL

    Raises:
        ValueError: If DATABASE_URL is not set
    """
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL not found in environment variables. "
            "Please set it in your .env file or environment. "
            "Format: postgresql://user:password@host:port/database"
        )

    return database_url


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


async def ensure_reminders_table(pool: asyncpg.Pool) -> None:
    """
    Ensure the reminders table exists in the database.

    Creates the table if it doesn't exist.

    Args:
        pool: Database connection pool

    Raises:
        asyncpg.exceptions.PostgresError: If table creation fails
    """
    logger = _get_logger()

    create_table_query = """
    CREATE TABLE IF NOT EXISTS reminders (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id BIGINT NOT NULL,
        message TEXT NOT NULL,
        reminder_date TIMESTAMP WITH TIME ZONE NOT NULL,
        timezone VARCHAR(50) NOT NULL DEFAULT 'GMT+3',
        recurring_pattern VARCHAR(20) NOT NULL DEFAULT 'NOT SPECIFIED',
        sent BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_reminders_user_id ON reminders(user_id);
    CREATE INDEX IF NOT EXISTS idx_reminders_reminder_date ON reminders(reminder_date);
    CREATE INDEX IF NOT EXISTS idx_reminders_sent ON reminders(sent);
    CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(reminder_date, sent) 
        WHERE sent = FALSE;
    """

    try:
        async with pool.acquire() as conn:
            await conn.execute(create_table_query)
            
            # Migration: Remove priority column if it exists (for existing databases)
            try:
                await conn.execute("""
                    ALTER TABLE reminders 
                    DROP COLUMN IF EXISTS priority;
                """)
                logger.info("Removed priority column from reminders table (if existed)")
            except Exception as migration_error:
                # Ignore if column doesn't exist or other migration errors
                logger.debug(f"Priority column migration: {migration_error}")
            
        logger.info("Ensured reminders table exists")
    except Exception as e:
        logger.error(f"Failed to create reminders table: {e}")
        raise
