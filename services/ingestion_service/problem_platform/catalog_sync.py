"""Update DocumentCatalog rows from synchronous Celery context."""

from __future__ import annotations

import logging
import uuid

from services.ingestion_service.db.problem_models import DocumentCatalog, DocumentIndexStatus
from services.ingestion_service.db.sync_engine import create_sync_engine_from_config

logger = logging.getLogger(__name__)


def mark_catalog_job_started(catalog_document_id: str, job_id: str) -> None:
    _, SessionLocal = create_sync_engine_from_config()
    with SessionLocal() as session:
        row = session.get(DocumentCatalog, uuid.UUID(catalog_document_id))
        if row:
            row.last_job_id = job_id
            row.index_status = DocumentIndexStatus.pending.value
            session.commit()


def mark_catalog_indexed_ok(catalog_document_id: str, chunks: int) -> None:
    _, SessionLocal = create_sync_engine_from_config()
    with SessionLocal() as session:
        row = session.get(DocumentCatalog, uuid.UUID(catalog_document_id))
        if row:
            row.index_status = DocumentIndexStatus.indexed.value
            row.chunks_indexed = chunks
            row.celery_error = None
            session.commit()


def mark_catalog_failed(catalog_document_id: str, err: str) -> None:
    _, SessionLocal = create_sync_engine_from_config()
    with SessionLocal() as session:
        row = session.get(DocumentCatalog, uuid.UUID(catalog_document_id))
        if row:
            row.index_status = DocumentIndexStatus.failed.value
            row.celery_error = err[:8192]
            session.commit()


def catalog_exists(catalog_document_id: str) -> bool:
    _, SessionLocal = create_sync_engine_from_config()
    with SessionLocal() as session:
        row = session.get(DocumentCatalog, uuid.UUID(catalog_document_id))
        return row is not None
