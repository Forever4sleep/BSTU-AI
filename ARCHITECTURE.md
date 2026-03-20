# BSTU-AI Architecture (High-Level)

```mermaid
flowchart TB
    subgraph Users
        Student[👤 Student]
        Admin[👤 Admin]
    end

    subgraph Interfaces
        TelegramBot[Telegram Bot<br/>Main student-facing]
        UploadBot[Upload Bot<br/>Admin document uploads]
        WebUI[Open WebUI<br/>planned]
    end

    subgraph Orchestrator
        IntentClassifier[Intent Classifier]
        IntentRouter[Intent Router]
    end

    subgraph Agents
        LearningAgent[Learning Agent<br/>RAG, quizzes, revision]
        AcademicAgent[Academic Agent<br/>profiles, courses]
        SchedulerAgent[Scheduler Agent<br/>reminders, deadlines]
    end

    subgraph Services
        ReminderService[Reminder Service<br/>polls DB, sends notifications]
        IngestionService[Ingestion Service<br/>parse → chunk → embed → index]
    end

    subgraph Data
        Postgres[(PostgreSQL<br/>reminders, schedules)]
        Qdrant[(Qdrant<br/>vector DB for RAG)]
    end

    Student --> TelegramBot
    Student -.-> WebUI
    Admin --> UploadBot

    TelegramBot --> IntentClassifier
    WebUI -.-> IntentClassifier
    IntentClassifier --> IntentRouter
    IntentRouter --> LearningAgent
    IntentRouter --> AcademicAgent
    IntentRouter --> SchedulerAgent

    LearningAgent --> Qdrant
    SchedulerAgent --> Postgres

    UploadBot -->|HTTP| IngestionService
    IngestionService --> Qdrant

    ReminderService -->|poll| Postgres
    ReminderService -->|send| TelegramBot

    style Student fill:#e1f5fe
    style Admin fill:#e1f5fe
    style Postgres fill:#fff3e0
    style Qdrant fill:#fff3e0
```

## Quick Reference

| Component | Purpose |
|-----------|---------|
| **Telegram Bot** | Main entry point; receives messages → orchestrator → agents |
| **Intent Classifier** | Extracts intents from natural language |
| **Intent Router** | Routes to Learning / Academic / Scheduler agent |
| **Learning Agent** | RAG over BSTU materials, quizzes, revision plans |
| **Academic Agent** | Professor profiles, course requirements |
| **Scheduler Agent** | Create/edit/delete reminders, deadlines |
| **Reminder Service** | Background: polls Postgres for due reminders → Telegram |
| **Ingestion Service** | FastAPI: upload docs → parse → chunk → embed → Qdrant |
| **Upload Bot** | Admin-only: forwards files to Ingestion Service |
