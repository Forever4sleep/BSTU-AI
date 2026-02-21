"""
Configuration for Ingestion Service

Handles loading configuration from environment variables.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_qdrant_host() -> str:
    """Get Qdrant host from environment."""
    return os.getenv("QDRANT_HOST", "localhost")


def get_qdrant_port() -> int:
    """Get Qdrant port from environment."""
    return int(os.getenv("QDRANT_PORT", "6333"))


def get_qdrant_collection_name() -> str:
    """Get Qdrant collection name from environment."""
    return os.getenv("QDRANT_COLLECTION_NAME", "bstu_materials")


def get_ingestion_service_port() -> int:
    """Get port for the Ingestion Service API."""
    return int(os.getenv("INGESTION_SERVICE_PORT", "8001"))


def get_materials_dir() -> Path:
    """Get path to temporary materials storage directory."""
    project_root = Path(__file__).parent.parent.parent
    materials_dir = project_root / "data" / "materials"
    materials_dir.mkdir(parents=True, exist_ok=True)
    return materials_dir


def get_embedding_api_key() -> str:
    """
    Get API key for embeddings.

    Uses OPENROUTER_API_KEY when using OpenRouter (default).
    Falls back to OPENAI_API_KEY for direct OpenAI.
    """
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY or OPENAI_API_KEY not found in environment variables. "
            "For OpenRouter embeddings, set OPENROUTER_API_KEY."
        )
    return api_key


def get_embedding_model() -> str:
    """Get embedding model name (OpenRouter format: provider/model)."""
    return os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")


def get_embedding_dimension() -> int:
    """
    Get embedding vector dimension.

    Must match the model output. Common values:
    - text-embedding-3-small: 1536
    - text-embedding-3-large: 3072
    - text-embedding-ada-002: 1536
    - Some OpenRouter models: 1024
    """
    return int(os.getenv("EMBEDDING_DIMENSION", "1536"))


def get_embedding_base_url() -> str:
    """
    Get embedding API base URL.

    Defaults to OpenRouter when OPENROUTER_API_KEY is set.
    Override with EMBEDDING_BASE_URL for custom endpoints.
    """
    custom = os.getenv("EMBEDDING_BASE_URL")
    if custom:
        return custom.rstrip("/")
    # Default to OpenRouter when using OpenRouter API key
    if os.getenv("OPENROUTER_API_KEY"):
        return "https://openrouter.ai/api/v1"
    # OpenAI default
    return "https://api.openai.com/v1"
