# Project Structure

This document outlines the folder structure of the BSTU-AI project.

## Overview

```
BSTU-AI/
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
├── data/                  # Data storage
│   ├── materials/        # BSTU learning materials (for RAG)
│   └── schedules/        # Schedule and deadline data
├── resources/             # Additional resources
├── tests/                 # Test suite
└── notebooks/             # Jupyter notebooks
```

## Directory Descriptions

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
Data storage directories:
- **`materials/`**: BSTU-specific learning materials for RAG
- **`schedules/`**: Schedule and deadline information

### `tests/`
Test suite for unit tests, integration tests, and test utilities.

### `notebooks/`
Jupyter notebooks for experimentation and analysis.
