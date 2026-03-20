# BSTU-AI Architecture (High-Level)

```mermaid
flowchart TB
    subgraph Users
        Student[Student]
        Admin[Admin]
    end

    subgraph Interfaces
        TelegramBot[Telegram Bot]
        UploadBot[Upload Bot]
        WebUI[Open WebUI planned]
    end

    subgraph Orchestrator
        IntentClassifier[Intent Classifier]
        IntentRouter[Intent Router]
    end

    subgraph Agents
        LearningAgent[Learning Agent]
        AcademicAgent[Academic Agent]
    end

    subgraph Services
        IngestionService[Ingestion Service]
    end

    subgraph Data
        Qdrant[(Qdrant)]
    end

    Student --> TelegramBot
    Student -.-> WebUI
    Admin --> UploadBot

    TelegramBot --> IntentClassifier
    WebUI -.-> IntentClassifier
    IntentClassifier --> IntentRouter
    IntentRouter --> LearningAgent
    IntentRouter --> AcademicAgent

    LearningAgent --> Qdrant

    UploadBot -->|HTTP| IngestionService
    IngestionService --> Qdrant
```

## Quick Reference

| Component | Purpose |
|-----------|---------|
| **Telegram Bot** | Main entry point; receives messages → orchestrator → agents |
| **Intent Classifier** | Extracts intents from natural language |
| **Intent Router** | Routes to Learning / Academic agent |
| **Learning Agent** | RAG over BSTU materials, quizzes, revision plans |
| **Academic Agent** | Professor profiles, course requirements |
| **Ingestion Service** | FastAPI: upload docs → parse → chunk → embed → Qdrant |
| **Upload Bot** | Admin-only: forwards files to Ingestion Service |
