"""
Indexer

Embeds text chunks and upserts them to Qdrant.
"""

import logging
import uuid
from pathlib import Path
from typing import List, Protocol

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from services.ingestion_service.processing.parsers import parse_document
from services.ingestion_service.processing.chunker import chunk_text

logger = logging.getLogger(__name__)


class EmbeddingsProtocol(Protocol):
    """Protocol for embeddings (embed_documents method)."""

    def embed_documents(self, texts: List[str]) -> List[List[float]]: ...


class DocumentIndexer:
    """Indexes documents into Qdrant via embedding and upsert."""

    def __init__(
        self,
        qdrant_client: QdrantClient,
        collection_name: str,
        embeddings: EmbeddingsProtocol,
    ):
        """
        Initialize the indexer.

        Args:
            qdrant_client: Qdrant client instance
            collection_name: Target collection name
            embeddings: Embeddings instance with embed_documents(texts) -> List[List[float]]
        """
        self.client = qdrant_client
        self.collection_name = collection_name
        self.embeddings = embeddings

    def index_file(
        self,
        file_path: Path,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        metadata: dict | None = None,
    ) -> int:
        """
        Parse, chunk, embed, and index a document file.

        Args:
            file_path: Path to the document
            chunk_size: Chunk size in characters
            chunk_overlap: Overlap between chunks
            metadata: Optional metadata to attach to all chunks

        Returns:
            Number of chunks indexed
        """
        logger.info(f"Indexer: starting for {file_path.name}")

        try:
            text = parse_document(file_path)
        except Exception as e:
            logger.error(f"Indexer: parse failed for {file_path.name}: {e}", exc_info=True)
            raise

        chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        if not chunks:
            logger.warning(f"Indexer: no chunks extracted from {file_path.name}")
            return 0

        logger.info(f"Indexer: embedding {len(chunks)} chunks via API")
        try:
            vectors = self.embeddings.embed_documents(chunks)
        except Exception as e:
            logger.error(
                f"Indexer: embedding failed for {file_path.name}, chunks={len(chunks)}: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            raise

        logger.info(f"Indexer: got {len(vectors)} vectors, building points for Qdrant")

        # Build points for Qdrant
        meta = metadata or {}
        meta["source_file"] = file_path.name

        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={
                    "text": chunk,
                    **meta,
                },
            )
            for chunk, vec in zip(chunks, vectors)
        ]

        logger.info(f"Indexer: upserting {len(points)} points to collection '{self.collection_name}'")
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
        except Exception as e:
            logger.error(
                f"Indexer: Qdrant upsert failed for {file_path.name}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise

        logger.info(f"Indexer: successfully indexed {len(points)} chunks from {file_path.name}")
        return len(points)
