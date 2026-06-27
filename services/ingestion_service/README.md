# Ingestion Service

> **Центральный backend BSTU-AI:** индексация документов, RAG-чат, платформа задач, OpenAI-совместимый прокси.

FastAPI-приложение на порту **8001**. Объединяет три зоны ответственности:

1. **Document ingestion** — приём файлов, асинхронная обработка (Celery), индексация в Qdrant.
2. **OpenAI-compatible API** — `/v1/chat/completions` с опциональным RAG для Open WebUI и встроенного чата платформы.
3. **Problem platform REST** — курсы, задачи, пользователи, отправки, AI-черновики.

---

## Архитектура внутри сервиса

```
FastAPI (main.py)
├── /api/*              routes.py       — upload, jobs, health, subjects
├── /v1/*               v1_routes.py    — models, chat/completions (+ RAG)
├── /api/platform/*     platform_routes — преподаватель + admin
└── /api/public/*       platform_routes — студент + unified login

Startup (lifespan):
  Qdrant client → ensure_collection
  DocumentIndexer (chunker + embeddings)
  RAGFactory.create("classic")
  PostgreSQL (async) — conversations + platform models

Background:
  Celery worker → process_document, draft/agent jobs
```

**PostgreSQL** хранит: диалоги (`ConversationRepository`), курсы, задачи, черновики, отправки, пользователей платформы.

**Qdrant:** глобальная коллекция `bstu_materials` (legacy upload bot) + **отдельная коллекция на курс** (`course_<slug>`) и коллекция опубликованных задач для античита.

---

## Пайплайн обработки документов

```
Файл → сохранение в data/materials/ → Celery task
  → Docling (VLM для PDF через OpenRouter, нативные бэкенды для Office/Markdown/…)
  → Chunking (sliding_window | recursive)
  → OpenRouter embeddings
  → Upsert в Qdrant (+ метаданные: subject, catalog_document_id, source_file)
```

| Этап | Детали |
|------|--------|
| Парсинг | Docling + VLM (`VLM_MODEL`, `VLM_CONCURRENCY`, `VLM_BATCH_SIZE`) |
| Chunking | `CHUNK_STRATEGY`, `CHUNK_SIZE`, `CHUNK_OVERLAP` |
| Эмбеддинги | `EMBEDDING_MODEL` через OpenRouter |
| Очередь | Celery + Redis (`CELERY_BROKER_URL`); worker `concurrency=1` для VLM PDF |

Поддерживаемые форматы: PDF, DOCX/DOC, PPTX, XLSX, MD, HTML, CSV, изображения (PNG, JPEG, …), TXT.

Статус задачи: `GET /api/jobs/{job_id}`.

---

## API

### Документы (глобальная загрузка)

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/upload` | Один документ → Celery |
| `POST` | `/api/upload/batch` | Пакетная загрузка |
| `GET` | `/api/jobs/{job_id}` | Статус Celery-задачи |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/subjects` | Предметы в глобальной коллекции |
| `GET` | `/api/collections` | Список коллекций Qdrant |

### OpenAI-совместимые

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/v1/models` | Список моделей |
| `POST` | `/v1/chat/completions` | Chat (streaming / non-streaming, RAG если `RAG_ENABLED`) |
| `POST` | `/v1/completions` | Legacy completions |

RAG для чата курса: JWT студента/преподавателя + query-параметр `bstu_course_slug` → retrieval из коллекции курса, Agent Checker при включённом античите.

### Платформа — преподаватель (`/api/platform`)

| Область | Примеры эндпоинтов |
|---------|-------------------|
| Auth | `POST /auth/login`, `POST /instructors/bootstrap` |
| Профиль | `GET/PATCH /me` |
| Курсы | `GET/POST /courses`, `PATCH /courses/{id}`, `PATCH /courses/{id}/settings` |
| Группы | `GET /study-groups`, `GET/PUT /courses/{id}/group-access` |
| Материалы | `POST /courses/{id}/upload`, `GET/DELETE /courses/{id}/documents/...` |
| Задачи | `GET /courses/{id}/problems-instructor`, `PATCH/DELETE .../problems/{id}` |
| Черновики | `POST .../draft-jobs`, `POST .../draft-agent-jobs`, `GET/PATCH /drafts/{id}`, `POST /drafts/{id}/publish` |
| Jobs | `GET /jobs/{job_id}` |
| Аналитика | `GET /analytics/dashboard` |

### Платформа — админ (`/api/platform/admin`)

| Область | Примеры |
|---------|---------|
| Auth | `POST /admin/auth/login` |
| Группы | CRUD `/admin/study-groups` |
| Студенты | CRUD `/admin/students`, rotate access key |
| Преподаватели | `POST /admin/instructors` |

### Платформа — студент (`/api/public`)

| Область | Примеры |
|---------|---------|
| Auth | `POST /session/login` (unified), `POST /auth/login` |
| Профиль | `GET/PATCH /me`, avatar |
| Курсы | `GET /my/courses`, `GET /courses/{slug}`, `GET /courses/{slug}/problems` |
| Задачи | `GET /problems/{id}`, `POST /problems/{id}/submit` |
| Прогресс | `GET /my/stats`, `/my/progress`, `/my/exam-prospect` |

Полная спецификация — в Swagger: http://localhost:8001/docs

---

## Модули

```
services/ingestion_service/
├── main.py                 # FastAPI app, lifespan
├── celery_app.py           # Celery instance
├── tasks.py                # process_document, draft jobs
├── qdrant_client.py        # Client, ensure_collection
├── api/
│   ├── routes.py           # /api upload & health
│   ├── v1_routes.py        # /v1 OpenAI proxy + RAG
│   ├── platform_routes.py  # /api/platform, /api/public
│   └── schemas.py
├── db/
│   ├── engine.py           # async SQLAlchemy
│   ├── models.py           # conversations
│   ├── problem_models.py   # courses, problems, users, …
│   └── repository.py
├── processing/
│   ├── parsers.py          # Docling + VLM
│   ├── chunker.py
│   ├── embeddings.py
│   └── indexer.py
└── problem_platform/
    ├── platform_auth.py    # JWT, passwords, API keys
    ├── code_judge.py       # Python test runner
    ├── problem_qdrant.py   # sync published problems to Qdrant
    ├── catalog_sync.py     # document index status in PG
    └── graphs/
        ├── draft_graph.py       # LangGraph: draft generation
        ├── agent_checker_graph.py  # anti-cheat before RAG chat
        └── reference_graph.py
```

---

## Конфигурация

### Инфраструктура

| Переменная | По умолчанию | Описание |
|------------|:------------:|----------|
| `INGESTION_SERVICE_PORT` | `8001` | Порт API |
| `QDRANT_HOST` / `QDRANT_PORT` | `localhost` / `6333` | Qdrant |
| `QDRANT_COLLECTION_NAME` | `bstu_materials` | Глобальная коллекция |
| `INGESTION_DB_URL` | — | PostgreSQL (asyncpg); без неё — нет платформы и диалогов |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Redis |
| `CORS_ORIGINS` | — | Origins для Vite UI |
| `LOG_LEVEL` | `INFO` | Логирование |

### Chunking и эмбеддинги

| Переменная | По умолчанию | Описание |
|------------|:------------:|----------|
| `CHUNK_STRATEGY` | `sliding_window` | `sliding_window` \| `recursive` |
| `CHUNK_SIZE` | `500` | Размер чанка |
| `CHUNK_OVERLAP` | `50` | Перекрытие |
| `OPENROUTER_API_KEY` | — | *обязательно* |
| `EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Модель эмбеддингов |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | LLM для `/v1` |

### VLM (PDF)

| Переменная | По умолчанию | Описание |
|------------|:------------:|----------|
| `VLM_MODEL` | `qwen/qwen-2.5-vl-7b-instruct` | VLM через OpenRouter |
| `VLM_TIMEOUT` | `120` | Таймаут запроса, сек |
| `VLM_CONCURRENCY` | `4` | Параллельных VLM-запросов на PDF |
| `VLM_BATCH_SIZE` | `4` | Страниц в batch Docling |

### RAG

См. [rag/README.md](../../rag/README.md) и `.env.example` (`RAG_*`, `RAG_PROBLEM_MATCH_*`).

### Платформа

| Переменная | Описание |
|------------|----------|
| `PLATFORM_JWT_SECRET` | HS256 для JWT |
| `PLATFORM_ADMIN_USERNAME` / `PLATFORM_ADMIN_PASSWORD` | Админ из `.env` |
| `PLATFORM_BOOTSTRAP_SECRET` | Bootstrap преподавателя |
| `CODE_JUDGE_TIMEOUT_SEC` | Таймаут Python judge |

---

## Запуск

### Docker (рекомендуется)

```bash
make up        # api + celery + postgres + redis + qdrant
make ui        # + frontend :5173
make health
```

### Локально

```bash
# Требуются: Qdrant, Redis, PostgreSQL
python -m services.ingestion_service.main

# Celery worker (отдельный терминал):
celery -A services.ingestion_service.celery_app worker --loglevel=info --concurrency=1
```

С uvicorn:

```bash
uvicorn services.ingestion_service.main:app --host 0.0.0.0 --port 8001
```

---

## Зависимости

- FastAPI, uvicorn, SQLAlchemy (async), Celery  
- qdrant-client, httpx  
- Docling (VLM pipeline)  
- LangChain, LangGraph, LangSmith  
- pypdf, python-docx (fallback paths)

См. [requirements.txt](../../requirements.txt).
