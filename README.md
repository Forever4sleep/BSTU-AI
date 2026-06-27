<p align="center">
  <strong>BSTU-AI</strong>
</p>
<p align="center">
  <em>Интеллектуальная платформа для обучения студентов БГТУ</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-18-61DAFB?style=flat&logo=react&logoColor=black" alt="React" />
  <img src="https://img.shields.io/badge/LangChain-0.3+-1C3C3C?style=flat" alt="LangChain" />
  <img src="https://img.shields.io/badge/OpenRouter-LLM-AB68FF?style=flat" alt="OpenRouter" />
  <img src="https://img.shields.io/badge/LangSmith-Tracing-00A67E?style=flat" alt="LangSmith" />
</p>

---

## О проекте

**BSTU-AI** — дипломный проект: платформа для студентов и преподавателей БГТУ с RAG-чатом по учебным материалам, задачами (код, тесты, свободный ответ), AI-генерацией черновиков заданий и администрированием курсов.

Центральный backend — **Ingestion Service** (FastAPI): индексация документов, OpenAI-совместимый чат, REST платформы задач и фоновые Celery-задачи.

Пользовательские интерфейсы:

| Интерфейс | Назначение |
|-----------|------------|
| **Problem Platform UI** (`frontend/`, :5173) | Основной веб-интерфейс: студенты, преподаватели, админ |
| **Open WebUI** (:3000, опционально) | Универсальный чат поверх `/v1/chat/completions` |
| **Telegram Bot** (опционально) | Классификация намерений; маршрутизация к агентам — в разработке |
| **Upload Bot** (опционально) | Загрузка материалов админами через Telegram |

---

## Технологический стек

| Компонент | Технология |
|-----------|------------|
| Backend | Python 3.11+, FastAPI, Celery |
| Frontend | React 18, TypeScript, Vite, Monaco Editor |
| LLM / эмбеддинги | OpenRouter (LangChain, LangGraph) |
| Векторная БД | Qdrant (глобальная коллекция + коллекции на курс) |
| Реляционная БД | PostgreSQL (диалоги, курсы, задачи, пользователи) |
| Очередь | Redis + Celery |
| Парсинг документов | Docling (VLM для PDF через OpenRouter) |
| RAG | Гибридный поиск (Dense + BM25), промпты из YAML |
| Трассировка | LangSmith |
| Контейнеризация | Docker Compose, Makefile |

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                        Интерфейсы                               │
│  Problem Platform UI   Open WebUI   Telegram Bot   Upload Bot   │
│       :5173               :3000          (bots)       (bots)    │
└────────────┬────────────────┬──────────────┬──────────────┬─────┘
             │                │              │              │
             └────────────────┴──────────────┴──────────────┘
                                    │
                          Ingestion Service :8001
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
              /api/upload      /api/platform      /v1/chat/completions
              /api/jobs        /api/public              │
                    │                 │            RAG (rag/)
                    ▼                 ▼                 ▼
              Celery Worker    PostgreSQL          OpenRouter
                    │          (platform + chats)
                    ▼
                 Qdrant
           (bstu_materials + course_*)
```

### Ingestion Service

Единая точка входа для:

- **Индексации материалов** — парсинг (Docling/VLM), chunking, эмбеддинги, upsert в Qdrant; асинхронно через Celery.
- **RAG-чата** — OpenAI-совместимый `/v1/chat/completions` с гибридным retrieval; per-course коллекции для чата по курсу.
- **Платформы задач** — курсы, группы, студенты, задачи, отправки, черновики, аналитика (`/api/platform`, `/api/public`).

Подробнее: [services/ingestion_service/README.md](services/ingestion_service/README.md).

### Problem Platform UI

React SPA в `frontend/`:

- **Студент** — курсы, решение задач (Monaco для Python), RAG-чат по материалам курса, личный кабинет.
- **Преподаватель** — управление курсами, загрузка материалов, публикация задач, AI-генерация черновиков, аналитика.
- **Администратор** — учётные группы, студенты, создание преподавателей.

API проксируется через Vite dev-server на Ingestion Service.

### RAG-пайплайн

Общая библиотека в `rag/`. Сборка через `RAGFactory`:

```python
from rag import RAGFactory

rag = RAGFactory.create("classic", qdrant_client=client)
# Per-course чат:
rag = RAGFactory.classic_for_collection(client, "course_algorithms", course_slug="algorithms")
```

```
Запрос пользователя
  → ContextualQueryProcessor (склеивает последние сообщения)
  → [Agent Checker — для чата курса: блокировка подсказок по заданиям]
  → HybridRetriever
      ├── DenseRetriever (Qdrant, косинусное сходство)
      └── SparseBM25Retriever (BM25 по корпусу из Qdrant)
      (fusion: alpha · dense + (1−alpha) · BM25, min-max нормализация)
  → ContextPromptBuilder (системное сообщение с найденными фрагментами)
  → LLM (через OpenRouter)
```

Подробнее: [rag/README.md](rag/README.md).

### Оркестратор и агенты (в разработке)

Задуманная мультиагентная модель (`orchestrator/`, `agents/`):

```
Сообщение → IntentClassifier (LLM) → IntentRouter → Агент → Ответ
```

Сейчас **IntentClassifier** работает в Telegram-боте; **IntentRouter** и агенты (Learning, Academic) — заготовки. Основной пользовательский функционал реализован через платформу задач и RAG-чат Ingestion Service.

---

## Платформа задач (кратко)

| Роль | Возможности |
|------|-------------|
| Админ | Группы, студенты, bootstrap преподавателей |
| Преподаватель | Курсы, материалы → Qdrant, задачи (coding / MCQ / free text), AI-черновики (LangGraph), публикация |
| Студент | Доступ по группе, решение задач, RAG-чат с античитом |

**Типы задач:** `coding` (Python + тесты), `mcq`, `free_text`.

**AI-черновики:** Celery + LangGraph (`draft_graph`) — отбор контекста из Qdrant курса и генерация пакета задач.

**Античит в чате:** Agent Checker (LangGraph) + опциональное cosine-сходство с условиями задач (`RAG_PROBLEM_MATCH_*`, режим в настройках курса: `off` / `basic` / `advanced`).

---

## Быстрый старт

### 1. Конфигурация

```bash
cp .env.example .env
# Обязательно: OPENROUTER_API_KEY
# Для платформы: PLATFORM_JWT_SECRET, PLATFORM_ADMIN_* , PLATFORM_BOOTSTRAP_SECRET
```

### 2. Docker Compose (рекомендуется)

```bash
make env          # .env из примера, если ещё нет
make up           # ядро: postgres, redis, qdrant, api, celery
make ui           # веб-платформа :5173
make webui        # Open WebUI :3000 (опционально)
make bots         # telegram + upload боты (опционально)
make stack-full   # всё сразу
```

После изменения `requirements.txt` или Dockerfile:

```bash
make up-build     # или make stack-full-build
```

### 3. Локальная разработка UI

```bash
cd frontend && npm install && npm run dev
# Vite проксирует API на localhost:8001 (см. frontend/.env.example)
```

### Проверка

| URL | Назначение |
|-----|------------|
| http://localhost:5173 | Problem Platform UI |
| http://localhost:8001/docs | Swagger (Ingestion Service) |
| http://localhost:8001/api/health | Health check |
| http://localhost:6333/dashboard | Qdrant Dashboard |
| http://localhost:3000 | Open WebUI (профиль `openwebui`) |

```bash
make health
curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"Привет!"}]}'
```

---

## Сервисы и профили Docker

| Сервис | Порт | Профиль | Описание |
|--------|:----:|:-------:|----------|
| **ingestion-service** | 8001 | *(ядро)* | FastAPI: upload, RAG, platform API, `/v1` |
| **celery-worker** | — | *(ядро)* | Индексация документов, draft/agent jobs |
| **postgres** | 5432 | *(ядро)* | Платформа + история диалогов |
| **redis** | 6379 | *(ядро)* | Брокер Celery |
| **qdrant** | 6333 | *(ядро)* | Векторная БД |
| **problem-platform-ui** | 5173 | `platform` | Vite + React frontend |
| **open-webui** | 3000 | `openwebui` | Внешний чат-клиент |
| **telegram-bot** | — | `bots` | Основной Telegram-бот |
| **upload-bot** | — | `bots` | Загрузка материалов в Telegram |

---

## Конфигурация RAG (`.env`)

| Переменная | По умолчанию | Описание |
|------------|:------------:|----------|
| `RAG_ENABLED` | `true` | RAG в `/v1/chat/completions` |
| `RAG_TOP_K` | `5` | Чанков после fusion |
| `RAG_BM25_K` | `5` | Top-k для BM25 |
| `RAG_BM25_MAX_DOCS` | `10000` | Макс. документов для BM25-корпуса |
| `RAG_HYBRID_ALPHA` | `0.5` | alpha·dense + (1−alpha)·BM25 |
| `RAG_RELEVANCE_THRESHOLD` | `0.0` | Мин. гибридный скор; ниже → отказ (0 = выкл.) |
| `RAG_QUERY_MAX_TURNS` | `3` | Сколько последних сообщений склеивать |
| `RAG_PROBLEM_MATCH_ENABLED` | `true` | Античит: сопоставление с задачами курса |
| `RAG_PROBLEM_MATCH_THRESHOLD` | `0.82` | Порог cosine для режима `basic` |
| `ENABLE_THINKING` | `true` | Reasoning у LLM (OpenRouter) |

Полный список переменных — в [.env.example](.env.example).

---

## Структура репозитория

```
BSTU-AI/
├── frontend/              # Problem Platform UI (React + Vite)
├── services/
│   ├── ingestion_service/ # Центральный FastAPI backend
│   └── upload_bot/        # Telegram-бот загрузки материалов
├── rag/                   # RAG: factory, retrievers, query, prompts
├── orchestrator/          # Классификация и маршрутизация намерений
├── agents/                # Learning / Academic агенты (заготовки)
├── interfaces/            # Telegram bot, webui-обёртки
├── prompts/               # YAML-промпты для RAG
├── config/                # Pydantic-конфиг из .env
├── shared/                # Схемы намерений, модели
├── data/materials/        # Временное хранилище файлов при индексации
└── docker-compose.yml     # Профили: platform, openwebui, bots
```

Подробнее: [STRUCTURE.md](STRUCTURE.md).

---

## Дорожная карта

<details>
<summary><strong>Платформа задач</strong></summary>

- [x] Курсы, группы, студенты, преподаватели, JWT-авторизация
- [x] Загрузка материалов курса → per-course Qdrant
- [x] Задачи: coding / MCQ / free text, публикация, отправки
- [x] Python code judge
- [x] AI-генерация черновиков (LangGraph + RAG-контекст)
- [x] RAG-чат по курсу с Agent Checker (античит)
- [x] Аналитика и прогресс студента
- [ ] Полная проверка free-text ответов агентом
- [ ] Расширенные типы задач и интеграции

</details>

<details>
<summary><strong>RAG и материалы</strong></summary>

- [x] Гибридный поиск (Dense + BM25)
- [x] Celery-пайплайн: Docling/VLM PDF, chunking, индексация
- [x] Per-course коллекции Qdrant
- [x] LangSmith-трассировка
- [x] История диалогов (PostgreSQL)
- [ ] GraphRAG и другие стратегии retrieval

</details>

<details>
<summary><strong>Оркестратор и Telegram-агенты</strong></summary>

- [x] LLM-классификация намерений (Telegram)
- [ ] IntentRouter → Learning Agent
- [ ] IntentRouter → Academic Agent
- [ ] Квизы, план повторения, профили преподавателей

</details>

<details>
<summary><strong>Инфраструктура</strong></summary>

- [x] Docker Compose + Makefile
- [x] OpenAI-совместимый API (`/v1`)
- [x] Open WebUI (опциональный профиль)
- [x] Upload Bot для материалов
- [ ] E2E-тесты и production-документация

</details>

---

## Статус проекта

Проект в активной разработке. Основной функционал сосредоточен в **Ingestion Service** и **Problem Platform UI**; мультиагентный оркестратор для Telegram — следующий этап.
