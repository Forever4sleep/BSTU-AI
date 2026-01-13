"""
Configuration for Reminder Service

Handles loading configuration from environment variables.
"""

import os
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_telegram_token() -> str:
    """
    Get Telegram bot token from environment variable.

    Returns:
        Telegram bot token

    Raises:
        ValueError: If token is not set
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN not found in environment variables. "
            "Please set it in your .env file or environment."
        )

    return token


def get_database_url() -> str:
    """
    Get PostgreSQL database connection URL from environment variable.

    Returns:
        Database connection URL

    Raises:
        ValueError: If DATABASE_URL is not set
    """
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL not found in environment variables. "
            "Please set it in your .env file or environment."
        )

    return database_url


def get_poll_interval() -> int:
    """
    Get poll interval in seconds from environment variable.

    Returns:
        Poll interval in seconds (defaults to 60)
    """
    return int(os.getenv("REMINDER_POLL_INTERVAL", "60"))
