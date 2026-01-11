"""
OpenRouter Configuration

Handles loading OpenRouter API key and model configuration.
"""

import os
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_openrouter_api_key() -> Optional[str]:
    """
    Get OpenRouter API key from environment variable.

    Returns:
        OpenRouter API key or None if not found

    Raises:
        ValueError: If API key is not set
    """
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY not found in environment variables. "
            "Please set it in your .env file or environment."
        )

    return api_key


def get_openrouter_model() -> str:
    """
    Get OpenRouter model name from environment variable.

    Returns:
        Model name (defaults to "openai/gpt-4o-mini" if not set)
    """
    return os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")


def get_openrouter_base_url() -> str:
    """
    Get OpenRouter base URL.

    Returns:
        OpenRouter API base URL
    """
    return "https://openrouter.ai/api/v1"
