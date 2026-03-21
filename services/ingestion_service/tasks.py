"""
Celery tasks for document processing.
"""

import logging
from pathlib import Path

from services.ingestion_service.celery_app import celery_app
from config import get_config
from services.ingestion_service.processing.chunker import create_chunker
from services.ingestion_service.processing.embeddings import OpenRouterEmbeddings
from services.ingestion_service.processing.indexer import DocumentIndexer
from services.ingestion_service.processing.parsers import parse_document
from services.ingestion_service.qdrant_client import create_qdrant_client, ensure_collection

logger = logging.getLogger(__name__)


def _get_indexer() -> DocumentIndexer:
    """Create indexer for use in worker process."""
    config = get_config()
    client = create_qdrant_client()
    ensure_collection(client)
    chunker = create_chunker(
        strategy=config.chunk_strategy,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )
    embeddings = OpenRouterEmbeddings()
    return DocumentIndexer(
        qdrant_client=client,
        collection_name=config.qdrant_collection_name,
        embeddings=embeddings,
        chunker=chunker,
    )


@celery_app.task(bind=True)
def process_document(
    self,
    file_path: str,
    subject: str,
    filename: str,
) -> dict:
    """
    Process and index a document file.

    Args:
        file_path: Path to the saved file
        subject: Subject metadata
        filename: Original filename for metadata

    Returns:
        dict with chunks_indexed, collection, filename
    """
    path = Path(file_path)
    try:
        indexer = _get_indexer()
        chunks_indexed = indexer.index_file(
            path,
            metadata={"subject": subject, "source_file": filename},
        )
        return {
            "chunks_indexed": chunks_indexed,
            "collection": indexer.collection_name,
            "filename": filename,
        }
    finally:
        if path.exists():
            try:
                path.unlink()
            except OSError as e:
                logger.warning(f"Failed to delete temp file {path}: {e}")
