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
from services.ingestion_service.problem_platform.upload_history import append_upload_failure
from services.ingestion_service.qdrant_client import create_qdrant_client, ensure_collection

logger = logging.getLogger(__name__)


def _get_indexer(*, collection_name: str | None) -> DocumentIndexer:
    """Create indexer for worker: отдельная коллекция на курс или глобальная из конфига."""
    config = get_config()
    client = create_qdrant_client()
    cn = (collection_name or "").strip() or config.qdrant_collection_name
    ensure_collection(client, collection_name=cn)
    chunker = create_chunker(
        strategy=config.chunk_strategy,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )
    embeddings = OpenRouterEmbeddings()
    return DocumentIndexer(
        qdrant_client=client,
        collection_name=cn,
        embeddings=embeddings,
        chunker=chunker,
    )


@celery_app.task(bind=True)
def process_document(
    self,
    file_path: str,
    subject: str,
    filename: str,
    catalog_document_id: str | None = None,
    collection_name: str | None = None,
    course_id: str | None = None,
    delete_file_after: bool = True,
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
    meta: dict = {"subject": subject, "source_file": filename}
    if catalog_document_id:
        meta["catalog_document_id"] = catalog_document_id
        try:
            from services.ingestion_service.problem_platform.catalog_sync import (
                mark_catalog_job_started,
            )

            mark_catalog_job_started(catalog_document_id, str(self.request.id))
        except Exception as e:
            logger.warning("catalog job mark failed: %s", e)

    cfg = get_config()
    try:
        indexer = _get_indexer(collection_name=collection_name)
        chunks_indexed = indexer.index_file(
            path,
            metadata=meta,
        )
        out = {
            "chunks_indexed": chunks_indexed,
            "collection": indexer.collection_name,
            "filename": filename,
            "catalog_document_id": catalog_document_id,
        }
        if catalog_document_id:
            try:
                from services.ingestion_service.problem_platform.catalog_sync import (
                    mark_catalog_indexed_ok,
                    mark_catalog_failed,
                )

                if chunks_indexed == 0:
                    err_msg = "no chunks produced (empty parse or too short)"
                    mark_catalog_failed(catalog_document_id, err_msg)
                    if course_id:
                        append_upload_failure(
                            history_dir=cfg.upload_history_dir,
                            course_id=course_id,
                            catalog_document_id=catalog_document_id,
                            filename=filename,
                            job_id=str(self.request.id),
                            error_message=err_msg,
                        )
                else:
                    mark_catalog_indexed_ok(catalog_document_id, chunks_indexed)
            except Exception as e:
                logger.warning("catalog update failed: %s", e)
        return out
    except Exception as exc:
        if catalog_document_id:
            try:
                from services.ingestion_service.problem_platform.catalog_sync import (
                    mark_catalog_failed,
                )

                mark_catalog_failed(catalog_document_id, str(exc))
            except Exception:
                pass
            if course_id:
                append_upload_failure(
                    history_dir=cfg.upload_history_dir,
                    course_id=course_id,
                    catalog_document_id=catalog_document_id,
                    filename=filename,
                    job_id=str(self.request.id),
                    error_message=str(exc),
                )
        raise
    finally:
        if delete_file_after and path.exists():
            try:
                path.unlink()
            except OSError as e:
                logger.warning(f"Failed to delete temp file {path}: {e}")
