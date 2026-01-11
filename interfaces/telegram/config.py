"""
Configuration for Telegram Bot

Handles loading Telegram bot token from environment variables or config.
"""

import os
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_telegram_token() -> Optional[str]:
    """
    Get Telegram bot token from environment variable.

    Returns:
        Telegram bot token or None if not found

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
