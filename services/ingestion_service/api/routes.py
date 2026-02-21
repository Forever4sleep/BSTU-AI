"""
API Routes for Ingestion Service

Upload and health check endpoints.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from services.ingestion_service.api.schemas import ErrorResponse, UploadResponse
from services.ingestion_service.config import get_materials_dir
from services.ingestion_service.processing.parsers import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ingestion"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    subject: str | None = Form(None),
) -> UploadResponse:
    """
    Upload a single document for processing and indexing.

    Accepts PDF, DOCX, and TXT files. The file is parsed, chunked,
    embedded, and indexed into Qdrant with optional subject metadata.
    """
    filename = file.filename or "unknown"
    logger.info(f"Upload started: filename={filename}, subject={subject}")

    if not subject or not subject.strip():
        raise HTTPException(status_code=400, detail="Subject is required")

    subject = subject.strip()

    suffix = Path(filename).suffix.lower()
    if suffix == ".doc":
        suffix = ".docx"

    if suffix not in SUPPORTED_EXTENSIONS:
        logger.warning(f"Rejected unsupported file type: {suffix}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    materials_dir = get_materials_dir()
    temp_path = materials_dir / filename

    try:
        contents = await file.read()
        file_size = len(contents)
        logger.info(f"Received file: {filename}, size={file_size} bytes")
        temp_path.write_bytes(contents)
        logger.debug(f"Saved to temp path: {temp_path}")

        indexer = request.app.state.indexer
        logger.info(f"Starting indexing pipeline for {filename}")
        chunks_indexed = indexer.index_file(temp_path, metadata={"subject": subject})

        logger.info(f"Upload completed: {filename}, chunks_indexed={chunks_indexed}")
        return UploadResponse(
            chunks_indexed=chunks_indexed,
            collection=indexer.collection_name,
            filename=filename,
        )
    except ValueError as e:
        logger.warning(f"Validation error during upload: filename={filename}, error={e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error processing upload: filename={filename}, error={type(e).__name__}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError as e:
                logger.warning(f"Failed to delete temp file {temp_path}: {e}")


@router.get("/health")
async def health_check(request: Request) -> dict:
    """
    Health check endpoint.

    Verifies connectivity to Qdrant.
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


@router.get("/subjects")
async def list_subjects(request: Request) -> dict:
    """
    List unique subject values from Qdrant collection payloads.

    Used by Upload Bot to show subject selection buttons.
    """
    try:
        client = request.app.state.qdrant_client
        collection_name = request.app.state.indexer.collection_name
        subjects: set[str] = set()
        offset = None

        while True:
            records, offset = client.scroll(
                collection_name=collection_name,
                limit=100,
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


@router.get("/collections")
async def list_collections(request: Request) -> dict:
    """List all Qdrant collections."""
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
