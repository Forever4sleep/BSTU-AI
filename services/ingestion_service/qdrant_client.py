"""
Qdrant Client for Ingestion Service

Handles connection to Qdrant and collection setup.
"""

import logging
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from config import get_config

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
    config = get_config()
    host = host or config.qdrant_host
    port = port or config.qdrant_port
    client = QdrantClient(host=host, port=port, timeout=30)
    logger.info(f"Connected to Qdrant at {host}:{port}")
    return client


def ensure_collection(
    client: QdrantClient,
    collection_name: Optional[str] = None,
    vector_size: Optional[int] = None,
) -> None:
    """
    Ensure the collection exists, creating it if necessary.

    Args:
        client: Qdrant client
        collection_name: Name of the collection (from config if None)
        vector_size: Dimension of embedding vectors (from config if None)
    """
    config = get_config()
    collection_name = collection_name or config.qdrant_collection_name
    vector_size = vector_size or config.embedding_dimension

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


def search_similar_points(
    client: QdrantClient,
    *,
    collection_name: str,
    vector: list[float],
    limit: int = 1,
) -> list[Any]:
    """Vector similarity search (qdrant-client 1.12+ uses query_points, not search)."""
    response = client.query_points(
        collection_name=collection_name,
        query=vector,
        limit=limit,
        with_payload=True,
    )
    return list(response.points or [])


def delete_catalog_document_chunks(
    client: QdrantClient,
    *,
    collection_name: str,
    catalog_document_id: str,
) -> None:
    """Remove all Qdrant points for one catalog document (best-effort if collection missing)."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    cn = collection_name.strip()
    doc_id = catalog_document_id.strip()
    if not cn or not doc_id:
        return
    try:
        collections = {c.name for c in client.get_collections().collections}
        if cn not in collections:
            return
        client.delete(
            collection_name=cn,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="metadata.catalog_document_id",
                        match=MatchValue(value=doc_id),
                    ),
                ],
            ),
        )
    except Exception:
        logger.warning(
            "Qdrant delete failed for collection=%s catalog_document_id=%s",
            cn,
            doc_id,
            exc_info=True,
        )
        raise
