<p align="center">
  <strong>BSTU-AI</strong>
</p>
<p align="center">
  <em>Интеллектуальная платформа для обучения студентов БГТУ</em>
</p>

A multi-agent AI system designed to help students automate academic tasks, accelerate learning, and enhance productivity.

## Purpose 

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

TO BE CONTINUED...
