# Project Structure

This document outlines the folder structure of the BSTU-AI project.

## Overview

```
BSTU-AI/
├── services/              # Standalone microservices
│   ├── reminder_service/  # Polls DB for due reminders, sends via Telegram
│   ├── ingestion_service/ # FastAPI: document upload, processing, Qdrant indexing
│   └── upload_bot/        # Telegram bot for admin document uploads to Ingestion Service
├── orchestrator/          # Intent extraction and routing
├── agents/                # Specialized agents
│   ├── learning/         # Learning Agent (RAG-based)
│   │   ├── rag/          # RAG implementation
│   │   └── quizzes/      # Quiz generation and grading
│   ├── academic/         # Academic Agent
│   │   ├── profiles/     # Professor profiles
│   │   └── courses/      # Course requirements
│   └── scheduler/        # Scheduler Agent
│       └── telegram/     # Telegram integration
├── shared/                # Shared utilities and models
│   ├── intents/          # Intent definitions
│   ├── models/           # Data models and schemas
│   └── utils/            # Utility functions
├── interfaces/            # User-facing entry points
│   ├── telegram/         # Telegram bot interface
│   └── webui/            # Open WebUI interface
├── config/                # Configuration files
├── data/                  # Temporary data storage
│   └── materials/        # Temporary storage for files being processed for RAG (deleted after indexing to Qdrant)
├── resources/             # Additional resources
├── tests/                 # Test suite
└── notebooks/             # Jupyter notebooks
```

## Directory Descriptions

### `services/`
Standalone microservices, each deployable independently:
- **`reminder_service/`**: Polls PostgreSQL for due reminders and sends them via Telegram
- **`ingestion_service/`**: FastAPI app for document upload, parsing, chunking, embedding, and indexing into Qdrant
- **`upload_bot/`**: Telegram bot (separate token) for admins to upload documents; forwards files to Ingestion Service API

### `orchestrator/`
Central component that extracts user intents and routes requests to appropriate agents.

### `agents/`
Contains all specialized agents, each following the single-responsibility principle.

- **`learning/`**: RAG-based learning agent with quiz functionality
- **`academic/`**: Academic information retrieval agent
- **`scheduler/`**: Deadline and reminder management agent

### `shared/`
Common code used across multiple components:
- **`intents/`**: Intent classification and definitions
- **`models/`**: Shared data models and schemas
- **`utils/`**: Utility functions and helpers

### `interfaces/`
User-facing entry points that connect users to the system:
- **`telegram/`**: Telegram bot interface for natural language interaction
- **`webui/`**: Open WebUI interface for web-based chat interaction

Both interfaces communicate with the orchestrator to handle user requests.

### `config/`
Configuration files and settings for the system.

### `data/`
Temporary data storage for processing:
- **`materials/`**: Temporary storage for source files (PDF, DOCX, TXT, etc.) during RAG processing. Files are stored here temporarily while being processed and indexed into Qdrant, then can be deleted. Schedules are stored exclusively in PostgreSQL.

### `tests/`
Test suite for unit tests, integration tests, and test utilities.

### `notebooks/`
Jupyter notebooks for experimentation and analysis.
