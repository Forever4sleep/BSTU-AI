"""
OpenRouter — re-export из config.
"""

from config import (
    get_openrouter_api_key,
    get_openrouter_base_url,
    get_openrouter_model,
)

__all__ = ["get_openrouter_api_key", "get_openrouter_base_url", "get_openrouter_model"]
