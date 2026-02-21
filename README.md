# BSTU-AI

A multi-agent AI system designed to help students automate academic tasks, accelerate learning, and enhance productivity.

---

## Overview

BSTU-AI is a diploma project that introduces an intelligent assistant system built on a multi-agent architecture. The system consists of specialized agents that handle different aspects of student life, all coordinated through a central orchestrator that understands user intent and routes requests appropriately.

The system is designed to work entirely through natural language interaction, with no button-based interfaces—just pure conversational interaction.

---

## Tech Stack

- **Language**: Python
- **LLM Framework**: LangChain, LangGraph
- **LLM Provider**: OpenRouter (currently)
- **Database**: Qdrant (for RAG), PostgreSQL (for structured data)
- **Interface**: Telegram Bot API, Open WebUI (planned)

---

## Architecture

The system follows a multi-agent architecture pattern where specialized agents handle distinct domains of functionality. All agents are managed by a central **orchestrator** that:

1. Extracts user intents from natural language input
2. Routes requests to the appropriate agent based on detected intents
3. Coordinates responses back to the user

---

## Agents

The system currently consists of three specialized agents, each with a clearly defined responsibility domain:

| Agent | Description |
|-------|-------------|
| **Learning Agent** | Helps students learn subjects faster using pre-loaded BSTU-specific materials (notes, lectures, etc.). Utilizes RAG (Retrieval-Augmented Generation) to provide context-aware explanations. Includes quiz generation and grading capabilities for better retention. |
| **Academic Agent** | Provides centralized access to academic information including professor profiles, course requirements, exam conditions, and evaluation criteria. |
| **Scheduler Agent** | Manages reminders and deadlines for coursework, exams, and other academic events. Fully natural-language driven with Telegram integration. | 

---

## Supported Intents

The system recognizes various intents that are routed to the appropriate agents. The intent list is continuously evolving as the project develops.

### Learning Agent Intents

| Intent | Description |
|--------|-------------|
| `learning.explain` | Explain a topic using BSTU-specific reference materials |
| `learning.summarize` | Create a summary of a topic or material |
| `learning.quiz.generate` | Generate a quiz to test the user's knowledge |
| `learning.quiz.grade` | Grade user's quiz answers and provide explanations for mistakes |
| `learning.plan.revision` | Propose a revision plan based on identified weak areas |

### Academic Agent Intents

| Intent | Description |
|--------|-------------|
| `academic.professor.profile` | Provide information about a professor and their courses |
| `academic.course.requirements` | List course requirements, exam conditions, and evaluation criteria |

### Scheduler Agent Intents

| Intent | Description |
|--------|-------------|
| `schedule.lookup` | Look up event dates or class schedules |
| `schedule.deadline.lookup` | Find deadlines for coursework or exams |
| `schedule.reminder.create` | Create a reminder for an upcoming event or deadline |
| `schedule.reminder.edit` | Edit an existing reminder |
| `schedule.reminder.delete` | Delete an existing reminder |
| `schedule.reminder.view` | View user's reminders (displays up to 5 reminders) |

---

## Project Status

This project is currently under active development. The intent list and functionality are continuously being expanded and refined.

---

## Running with Docker Compose

Run the entire system (PostgreSQL, Qdrant, main bot, reminder service, ingestion service, upload bot) with one command:

```bash
cp .env.example .env
# Edit .env and set your API keys and bot tokens
docker compose up --build
```

Services:
- **telegram-bot** – Main student-facing bot
- **reminder-service** – Polls for due reminders, sends via Telegram
- **ingestion-service** – FastAPI at http://localhost:8001 for document upload
- **upload-bot** – Admin bot for uploading documents to RAG
- **postgres** – PostgreSQL on port 5432
- **qdrant** – Vector DB on port 6333

**Web UIs:**
- **Qdrant dashboard** – http://localhost:6333/dashboard
- **FastAPI Swagger UI** – http://localhost:8001/docs

Postgres defaults: `postgresql://bstu:bstu@postgres:5432/bstu_ai` (overridden in compose).

---

## Development Roadmap

### Core Agent Implementation

#### Learning Agent
- [ ] Implement Learning Agent core functionality (RAG-based explanations and summaries)
- [ ] Set up Qdrant vector database configuration and connection
- [ ] Implement RAG pipeline for Learning Agent (document loading, chunking, embedding, indexing)
- [ ] Implement quiz generation functionality for Learning Agent (`learning.quiz.generate` intent)
- [ ] Implement quiz grading functionality for Learning Agent (`learning.quiz.grade` intent)
- [ ] Implement revision planning functionality for Learning Agent (`learning.plan.revision` intent)

#### Academic Agent
- [ ] Implement Academic Agent core functionality (professor profiles and course requirements)
- [ ] Create database schema and models for academic data (professors, courses, requirements)
- [ ] Implement professor profile retrieval (`academic.professor.profile` intent)
- [ ] Implement course requirements retrieval (`academic.course.requirements` intent)

#### Scheduler Agent
- [x] Implement reminder creation (`schedule.reminder.create` intent)
- [x] Implement reminder editing (`schedule.reminder.edit` intent)
- [x] Implement reminder deletion (`schedule.reminder.delete` intent)
- [x] Implement reminder viewing (`schedule.reminder.view` intent)
- [ ] Complete Scheduler Agent: implement `schedule.lookup` and `schedule.deadline.lookup` intents

### Infrastructure & Configuration

- [ ] Add missing dependencies to requirements.txt (qdrant-client, langgraph, embeddings library, etc.)
- [ ] Add configuration management for Qdrant connection (host, port, collection name)
- [ ] Add environment variable validation and startup checks

### Integration & Routing

- [ ] Update IntentRouter to route Learning Agent intents (`learning.explain`, `learning.summarize`, etc.)
- [ ] Update IntentRouter to route Academic Agent intents (`academic.professor.profile`, `academic.course.requirements`)

### Interfaces

- [ ] Implement Open WebUI interface (`interfaces/webui/`)

### Data & Processing

- [ ] Create data ingestion pipeline for loading BSTU materials into RAG system
- [ ] Implement document processing utilities (PDF, DOCX, TXT parsers) for RAG

### Testing

- [ ] Create unit tests for IntentClassifier
- [ ] Create unit tests for IntentRouter
- [ ] Create unit tests for Scheduler Agent
- [ ] Create unit tests for Learning Agent
- [ ] Create unit tests for Academic Agent
- [ ] Create integration tests for end-to-end workflows

### Quality & Operations

- [ ] Add error handling and logging improvements across all agents
- [ ] Create shared utilities module (`shared/utils/`) with common helper functions
- [ ] Add API rate limiting and error recovery mechanisms
- [ ] Implement conversation context/memory for multi-turn interactions
- [ ] Create deployment documentation and setup instructions

---

**Legend:**
- [x] Completed
- [ ] Pending
