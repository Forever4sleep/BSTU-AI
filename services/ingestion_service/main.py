"""
Ingestion Service Main Entry Point

FastAPI application for document upload, processing, and Qdrant indexing.

Usage:
    python -m services.ingestion_service.main
    or: uvicorn services.ingestion_service.main:app --host 0.0.0.0 --port 8001
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from services.ingestion_service.api.routes import router
from services.ingestion_service.config import (
    get_embedding_dimension,
    get_ingestion_service_port,
    get_materials_dir,
    get_qdrant_collection_name,
)
from services.ingestion_service.processing.indexer import DocumentIndexer
from services.ingestion_service.qdrant_client import (
    create_qdrant_client,
    ensure_collection,
)

def _get_log_level() -> int:
    import os
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level, logging.INFO)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=_get_log_level(),
)
logger = logging.getLogger(__name__)

# Reduce httpx noise (set LOG_LEVEL=DEBUG to see HTTP requests)
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup, cleanup on shutdown."""
    logger.info("Initializing Ingestion Service...")

    # Ensure materials directory exists
    get_materials_dir()

    # Create Qdrant client and ensure collection
    client = create_qdrant_client()
    collection_name = get_qdrant_collection_name()
    ensure_collection(client, collection_name, vector_size=get_embedding_dimension())

    # Create embeddings (OpenRouter via direct HTTP) and indexer
    from services.ingestion_service.processing.embeddings import OpenRouterEmbeddings

    embeddings = OpenRouterEmbeddings()
    indexer = DocumentIndexer(
        qdrant_client=client,
        collection_name=collection_name,
        embeddings=embeddings,
    )

    app.state.qdrant_client = client
    app.state.indexer = indexer

    logger.info("Ingestion Service initialized successfully")
    yield
    logger.info("Shutting down Ingestion Service")


app = FastAPI(
    title="BSTU-AI Ingestion Service",
    description="Document upload and indexing for RAG pipelines",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "ingestion",
        "status": "running",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    port = get_ingestion_service_port()
    uvicorn.run(
        "services.ingestion_service.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
