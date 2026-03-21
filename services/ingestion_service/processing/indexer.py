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

from services.ingestion_service.processing.chunker import ChunkerStrategy
from services.ingestion_service.processing.parsers import parse_document

logger = logging.getLogger(__name__)


class EmbeddingsProtocol(Protocol):
    """Protocol for embeddings (embed_documents method)."""

    def embed_documents(self, texts: List[str]) -> List[List[float]]: ...


class DocumentIndexer:
    """
    Context for chunking: holds a ChunkerStrategy and delegates chunking to it.

    Follows Strategy pattern (refactoring.guru). Strategy can be swapped at runtime.
    """

    def __init__(
        self,
        qdrant_client: QdrantClient,
        collection_name: str,
        embeddings: EmbeddingsProtocol,
        chunker: ChunkerStrategy,
    ):
        self.client = qdrant_client
        self.collection_name = collection_name
        self.embeddings = embeddings
        self._chunker = chunker

    @property
    def chunker(self) -> ChunkerStrategy:
        return self._chunker

    @chunker.setter
    def chunker(self, strategy: ChunkerStrategy) -> None:
        self._chunker = strategy

    def index_file(
        self,
        file_path: Path,
        metadata: dict | None = None,
    ) -> int:
        """
        Parse, chunk, embed, and index a document file.

        Args:
            file_path: Path to the document
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

        text_len = len(text) if text else 0
        text_preview = (text or "")[:200].replace("\n", " ")
        logger.info(f"Indexer: parsed {text_len} chars from {file_path.name}, preview: {text_preview!r}...")

        chunks = self._chunker.chunk(text)

        if not chunks:
            logger.warning(
                f"Indexer: no chunks from {file_path.name} "
                f"(parsed {text_len} chars - empty or too short for chunk_size)"
            )
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

        meta = dict(metadata or {})
        if "source_file" not in meta:
            meta["source_file"] = file_path.name

        # LangChain QdrantVectorStore expects text under `text` and metadata nested.
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={
                    "text": chunk,
                    "metadata": dict(meta),
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
