"""
Qdrant Client for Ingestion Service

Handles connection to Qdrant and collection setup.
"""

import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from services.ingestion_service.config import (
    get_embedding_dimension,
    get_qdrant_collection_name,
    get_qdrant_host,
    get_qdrant_port,
)

logger = logging.getLogger(__name__)


def create_qdrant_client(
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> QdrantClient:
    """
    Create and return a Qdrant client.

    Args:
        host: Qdrant host (default from config)
        port: Qdrant port (default from config)

    Returns:
        Configured QdrantClient instance
    """
    host = host or get_qdrant_host()
    port = port or get_qdrant_port()
    client = QdrantClient(host=host, port=port, timeout=30)
    logger.info(f"Connected to Qdrant at {host}:{port}")
    return client


def ensure_collection(
    client: QdrantClient,
    collection_name: str,
    vector_size: int | None = None,
) -> None:
    """
    Ensure the collection exists, creating it if necessary.

    Args:
        client: Qdrant client
        collection_name: Name of the collection
        vector_size: Dimension of embedding vectors (from config if None)
    """
    vector_size = vector_size or get_embedding_dimension()
    collections = client.get_collections().collections
    existing = [c.name for c in collections]

    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created collection '{collection_name}' with vector size {vector_size}")
