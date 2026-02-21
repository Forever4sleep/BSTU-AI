"""
Configuration for Upload Bot

Handles loading configuration from environment variables.
"""

import os
from typing import List

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_upload_bot_token() -> str:
    """
    Get Upload Bot token from environment variable.

    Returns:
        Telegram bot token for the upload bot

    Raises:
        ValueError: If token is not set
    """
    token = os.getenv("UPLOAD_BOT_TOKEN")

    if not token:
        raise ValueError(
            "UPLOAD_BOT_TOKEN not found in environment variables. "
            "Please set it in your .env file or environment."
        )

    return token


def get_ingestion_service_url() -> str:
    """
    Get Ingestion Service base URL from environment variable.

    Returns:
        Base URL (e.g. http://localhost:8001)

    Raises:
        ValueError: If URL is not set
    """
    url = os.getenv("INGESTION_SERVICE_URL")

    if not url:
        raise ValueError(
            "INGESTION_SERVICE_URL not found in environment variables. "
            "Please set it in your .env file or environment."
        )

    return url.rstrip("/")


def get_allowed_upload_user_ids() -> List[int]:
    """
    Get list of Telegram user IDs allowed to upload documents.

    Returns:
        List of user IDs, or empty list if all users are allowed
    """
    raw = os.getenv("ALLOWED_UPLOAD_USER_IDS", "")
    if not raw.strip():
        return []
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        return []
