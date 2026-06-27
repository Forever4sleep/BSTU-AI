"""
Ingestion Service Main Entry Point

FastAPI application for document upload, processing, and Qdrant indexing.

Usage:
    python -m services.ingestion_service.main
    or: uvicorn services.ingestion_service.main:app --host 0.0.0.0 --port 8001
"""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import get_config
from rag import RAGFactory
from services.ingestion_service.api.platform_routes import platform_router, public_router
from services.ingestion_service.api.routes import router
from services.ingestion_service.api.v1_routes import router as v1_router
from services.ingestion_service.db.engine import create_db_engine, create_session_factory, init_db
from services.ingestion_service.db.repository import ConversationRepository
from services.ingestion_service.processing.chunker import create_chunker
from services.ingestion_service.processing.indexer import DocumentIndexer
from services.ingestion_service.qdrant_client import (
    create_qdrant_client,
    ensure_collection,
)


def _get_log_level() -> int:
    level = get_config().log_level.upper()
    return getattr(logging, level, logging.INFO)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=_get_log_level(),
)
logger = logging.getLogger(__name__)

# Reduce httpx noise (set LOG_LEVEL=DEBUG to see HTTP requests)
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize services on startup, cleanup on shutdown."""
    logger.info("Initializing Ingestion Service...")
    config = get_config()

    # Ensure materials directory exists
    config.materials_dir

    # Create Qdrant client and ensure collection
    client = create_qdrant_client()
    ensure_collection(client)

    # Create chunker, embeddings, and indexer
    from services.ingestion_service.processing.embeddings import OpenRouterEmbeddings

    chunker = create_chunker(
        strategy=config.chunk_strategy,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )
    embeddings = OpenRouterEmbeddings()
    indexer = DocumentIndexer(
        qdrant_client=client,
        collection_name=config.qdrant_collection_name,
        embeddings=embeddings,
        chunker=chunker,
    )

    app.state.qdrant_client = client
    app.state.indexer = indexer
    app.state.embeddings = embeddings
    app.state.rag = RAGFactory.create("classic", qdrant_client=client)

    if config.ingestion_db_url:
        db_engine = create_db_engine(config.ingestion_db_url)
        await init_db(db_engine)
        session_factory = create_session_factory(db_engine)
        app.state.conversation_repo = ConversationRepository(session_factory)
        app.state.session_factory = session_factory
        app.state.db_engine = db_engine
        logger.info("PostgreSQL conversation storage initialized")
    else:
        app.state.conversation_repo = None
        app.state.session_factory = None
        app.state.db_engine = None
        logger.warning("INGESTION_DB_URL not set — conversation/problem DB disabled")

    logger.info("Ingestion Service initialized successfully")
    yield

    if app.state.db_engine is not None:
        await app.state.db_engine.dispose()

    try:
        from langsmith import Client as _LSClient

        _LSClient().flush()
        logger.info("LangSmith traces flushed")
    except Exception:
        pass

    logger.info("Shutting down Ingestion Service")


app = FastAPI(
    title="BSTU-AI API",
    description="Загрузка документов, RAG-индексация в Qdrant, OpenAI-совместимый прокси для OpenWebUI",
    version="0.2.0",
    lifespan=lifespan,
)

_cfg = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cfg.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(v1_router)
app.include_router(platform_router)
app.include_router(public_router)


@app.get("/", summary="Корневой эндпоинт")
async def root():
    """Информация о сервисе и доступных эндпоинтах."""
    return {
        "service": "bstu-ai-api",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "upload": "/api/upload",
            "upload_batch": "/api/upload/batch",
            "job_status": "/api/jobs/{job_id}",
            "chat": "/v1/chat/completions (RAG if RAG_ENABLED)",
            "models": "/v1/models",
            "platform_teacher": "/api/platform/",
            "platform_admin_create_instructor": "POST /api/platform/admin/instructors",
            "platform_student_public": "/api/public/",
            "platform_admin_login": "/api/platform/admin/auth/login",
            "unified_login": "POST /api/public/session/login",
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = get_config().ingestion_service_port
    uvicorn.run(
        "services.ingestion_service.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
