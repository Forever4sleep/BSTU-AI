"""
API Routes for Ingestion Service

Upload and health check endpoints.
"""

import logging
import uuid
from pathlib import Path

from celery.result import AsyncResult
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from services.ingestion_service.api.schemas import (
    BatchUploadResponse,
    ErrorResponse,
    JobStatusResponse,
    UploadResponse,
)
from config import get_config
from services.ingestion_service.processing.parsers import SUPPORTED_EXTENSIONS
from services.ingestion_service.celery_app import celery_app
from services.ingestion_service.tasks import process_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Загрузка документов"])


def _validate_file(filename: str) -> None:
    """Validate file extension. Raises HTTPException if invalid."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".doc":
        suffix = ".docx"
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Загрузить документ",
)
async def upload_document(
    file: UploadFile = File(..., description="Файл (PDF, DOCX, PPTX, XLSX, MD, HTML, CSV, изображения, TXT)"),
    subject: str | None = Form(None, description="Предмет / тема документа"),
) -> UploadResponse:
    """
    Загрузка одного документа для обработки и индексации.

    Файл сохраняется и ставится в очередь Celery. Используйте GET /api/jobs/{job_id}
    для проверки статуса.
    """
    filename = file.filename or "unknown"
    logger.info(f"Upload started: filename={filename}, subject={subject}")

    if not subject or not subject.strip():
        raise HTTPException(status_code=400, detail="Subject is required")

    subject = subject.strip()
    _validate_file(filename)

    materials_dir = get_config().materials_dir
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    temp_path = materials_dir / unique_name

    try:
        contents = await file.read()
        file_size = len(contents)
        logger.info(f"Received file: {filename}, size={file_size} bytes")
        temp_path.write_bytes(contents)

        task = process_document.delay(
            str(temp_path),
            subject,
            filename,
        )
        job_id = task.id
        logger.info(f"Enqueued job {job_id} for {filename}")

        return UploadResponse(
            job_id=job_id,
            filename=filename,
            status="pending",
        )
    except ValueError as e:
        logger.warning(f"Validation error during upload: filename={filename}, error={e}")
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error processing upload: filename={filename}, error={type(e).__name__}: {e}",
            exc_info=True,
        )
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/upload/batch",
    response_model=BatchUploadResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Пакетная загрузка документов",
)
async def upload_documents_batch(
    files: list[UploadFile] = File(..., description="Список файлов (PDF, DOCX, PPTX, XLSX, MD, HTML, CSV, изображения, TXT)"),
    subject: str | None = Form(None, description="Предмет для всех файлов"),
) -> BatchUploadResponse:
    """
    Пакетная загрузка документов для асинхронной обработки.

    Все файлы ставятся в очередь Celery. Используйте GET /api/jobs/{job_id} для статуса.
    """
    if not subject or not subject.strip():
        raise HTTPException(status_code=400, detail="Subject is required")

    subject = subject.strip()

    for f in files:
        if f.filename:
            _validate_file(f.filename)

    materials_dir = get_config().materials_dir
    job_ids: list[str] = []

    for file in files:
        filename = file.filename or "unknown"
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        temp_path = materials_dir / unique_name

        try:
            contents = await file.read()
            logger.info(f"Batch: queuing {filename}, size={len(contents)} bytes")
            temp_path.write_bytes(contents)

            task = process_document.delay(str(temp_path), subject, filename)
            job_ids.append(task.id)
        except Exception as e:
            logger.error(f"Batch: failed to enqueue {filename}: {e}", exc_info=True)
            try:
                temp_path.unlink()
            except OSError:
                pass
            raise HTTPException(status_code=500, detail=str(e))

    return BatchUploadResponse(
        files_queued=len(job_ids),
        job_ids=job_ids,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Статус задачи обработки",
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """
    Проверить статус задачи обработки документа.

    Возвращает PENDING, STARTED, SUCCESS или FAILURE.
    При успехе — chunks_indexed и collection.
    """
    result = AsyncResult(job_id, app=celery_app)
    status = result.status

    resp = JobStatusResponse(job_id=job_id, status=status)

    if status == "SUCCESS" and result.successful():
        data = result.result
        if isinstance(data, dict):
            resp.filename = data.get("filename")
            resp.chunks_indexed = data.get("chunks_indexed")
            resp.collection = data.get("collection")
    elif status == "FAILURE" and result.failed():
        resp.error = str(result.result) if result.result else "Unknown error"

    return resp


@router.get("/health", summary="Проверка здоровья")
async def health_check(request: Request) -> dict:
    """
    Проверка работоспособности сервиса.

    Проверяет подключение к Qdrant.
    """
    try:
        client = request.app.state.qdrant_client
        collections = client.get_collections()
        return {
            "status": "healthy",
            "qdrant_connected": True,
            "collections_count": len(collections.collections),
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "qdrant_connected": False,
            "error": str(e),
        }


@router.get("/subjects", summary="Список предметов")
async def list_subjects(request: Request) -> dict:
    """
    Список уникальных предметов из метаданных в Qdrant.

    Используется Upload Bot для кнопок выбора предмета.
    """
    try:
        client = request.app.state.qdrant_client
        collection_name = request.app.state.indexer.collection_name
        subjects: set[str] = set()
        offset = None

        while True:
            records, offset = client.scroll(
                collection_name=collection_name,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                if record.payload and "subject" in record.payload:
                    subj = record.payload["subject"]
                    if isinstance(subj, str) and subj.strip():
                        subjects.add(subj.strip())
            if offset is None:
                break

        return {"subjects": sorted(subjects)}
    except Exception as e:
        logger.error(f"Failed to list subjects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections", summary="Список коллекций")
async def list_collections(request: Request) -> dict:
    """Список всех коллекций Qdrant."""
    try:
        client = request.app.state.qdrant_client
        collections = client.get_collections()
        return {
            "collections": [
                {"name": c.name, "vectors_count": c.vectors_count}
                for c in collections.collections
            ]
        }
    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))
