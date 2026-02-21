# Ingestion Service

Standalone FastAPI microservice for document upload, processing, and indexing into Qdrant for RAG pipelines.

## Overview

The Ingestion Service receives documents via HTTP, parses them (PDF, DOCX, TXT), chunks the text, embeds chunks using an embedding model, and upserts them into a Qdrant collection.

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `QDRANT_HOST` | Qdrant server host | `localhost` |
| `QDRANT_PORT` | Qdrant server port | `6333` |
| `QDRANT_COLLECTION_NAME` | Target collection name | `bstu_materials` |
| `INGESTION_SERVICE_PORT` | API server port | `8001` |
| `OPENROUTER_API_KEY` | API key for embeddings (OpenRouter) | Required |
| `EMBEDDING_MODEL` | Embedding model (OpenRouter format) | `openai/text-embedding-3-small` |
| `EMBEDDING_BASE_URL` | Optional override for embedding API | `https://openrouter.ai/api/v1` when using OpenRouter |
| `LOG_LEVEL` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) | `INFO` |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upload` | Upload single document (multipart/form-data) |
| GET | `/api/health` | Health check (Qdrant connectivity) |
| GET | `/api/collections` | List Qdrant collections |

## Running the Service

```bash
python -m services.ingestion_service.main
```

Or with uvicorn:

```bash
uvicorn services.ingestion_service.main:app --host 0.0.0.0 --port 8001
```

## Architecture

- **Parsers**: Extract text from PDF (pypdf), DOCX (python-docx), TXT
- **Chunker**: Fixed-size chunks with overlap (500 chars, 50 overlap by default)
- **Embeddings**: OpenRouter (OpenAI-compatible API, uses OPENROUTER_API_KEY)
- **Indexer**: Upserts vectors to Qdrant with metadata (source_file, etc.)

## Dependencies

- FastAPI, uvicorn
- qdrant-client
- pypdf, python-docx
- langchain-openai (for embeddings)
