<p align="center">
  <strong>BSTU-AI</strong>
</p>
<p align="center">
  <em>Интеллектуальный ассистент для студентов БГТУ</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/LangChain-0.3+-1C3C3C?style=flat" alt="LangChain" />
  <img src="https://img.shields.io/badge/OpenRouter-LLM-AB68FF?style=flat" alt="OpenRouter" />
  <img src="https://img.shields.io/badge/LangSmith-Tracing-00A67E?style=flat" alt="LangSmith" />
</p>

---

## О проекте

**BSTU-AI** — дипломный проект, представляющий систему умного помощника для студентов БГТУ. Архитектура построена на специализированных агентах, каждый из которых отвечает за свою область: учёба и академическая информация.

> Взаимодействие с системой происходит **полностью на естественном языке** — без кнопок и форм, только диалог.

---

## Технологический стек

| Компонент | Технология |
|-----------|------------|
| Язык | Python 3.11+ |
| LLM-фреймворк | LangChain |
| Провайдер LLM | OpenRouter |
| Базы данных | Qdrant (векторная), PostgreSQL (история диалогов) |
| RAG | Гибридный поиск (Dense + BM25), промпты из YAML |
| Трассировка | LangSmith |
| Очередь задач | Celery + Redis |
| Интерфейс | Telegram Bot API, Open WebUI (чат) |

---

## Архитектура

Центральный **оркестратор** управляет всеми агентами и:

1. **Распознаёт намерения** пользователя из текста сообщения
2. **Маршрутизирует запросы** к нужному агенту
3. **Формирует ответ** и возвращает его пользователю

```
Сообщение → Классификация намерений → Роутер → Агент → Ответ
```

---

## RAG-пайплайн

Ingestion Service предоставляет OpenAI-совместимый API (`/v1/chat/completions`), через который **Open WebUI** общается с LLM. Перед отправкой запроса к LLM срабатывает RAG-пайплайн:

```
Запрос пользователя
  → ContextualQueryProcessor (склеивает последние сообщения)
  → HybridRetriever
      ├── DenseRetriever (Qdrant, косинусное сходство)
      └── SparseBM25Retriever (BM25 по корпусу из Qdrant)
      (fusion: alpha · dense + (1−alpha) · BM25, min-max нормализация)
  → ContextPromptBuilder (системное сообщение с найденными фрагментами)
  → LLM (через OpenRouter)
```

### Ключевые особенности

- **Factory-паттерн** — `RAGFactory.create("classic", qdrant_client=client)` собирает `ClassicRAG` из компонентов через DI. Для нового типа (например, `GraphRAG`) достаточно реализовать `BaseRAG` и зарегистрировать через `RAGFactory.register()`.
- **Гибридный поиск** — взвешенная линейная комбинация нормализованных скоров Dense и BM25 (параметр `RAG_HYBRID_ALPHA`).
- **Порог релевантности** — если лучший гибридный скор ниже `RAG_RELEVANCE_THRESHOLD`, модель отвечает отказом вместо галлюцинации.
- **История диалога** — последние сообщения учитываются при формировании запроса к retriever; диалоги сохраняются в PostgreSQL.
- **Промпты из YAML** — системные инструкции для RAG загружаются из `prompts/classified_rag.yaml`, на русском языке.
- **LangSmith-трассировка** — полная видимость пайплайна: запрос, история, найденные чанки, скоры (dense, BM25, hybrid), ответ LLM.

---

## Агенты системы

| Агент | Описание |
|-------|----------|
| **Learning Agent** | Помогает быстрее осваивать предметы на основе материалов БГТУ (лекции, конспекты). Использует RAG для контекстных объяснений. Генерирует и проверяет тесты. |
| **Academic Agent** | Централизованный доступ к академической информации: профили преподавателей, требования к курсам, условия экзаменов, критерии оценивания. |

---

## Поддерживаемые намерения

### Learning Agent

| Намерение | Описание |
|-----------|----------|
| `learning.explain` | Объяснение темы по материалам БГТУ |
| `learning.summarize` | Краткое изложение темы или материала |
| `learning.quiz.generate` | Генерация теста для проверки знаний |
| `learning.quiz.grade` | Проверка ответов на тест с пояснениями ошибок |
| `learning.plan.revision` | План повторения на основе слабых мест |

### Academic Agent

| Намерение | Описание |
|-----------|----------|
| `academic.professor.profile` | Информация о преподавателе и его курсах |
| `academic.course.requirements` | Требования к курсу, условия экзамена, критерии оценивания |

---

## Быстрый старт

### Запуск через Docker Compose

```bash
cp .env.example .env
# Обязательно: OPENROUTER_API_KEY в .env
docker compose up --build
```

По умолчанию запускаются все основные сервисы: **qdrant**, **postgres**, **redis**, **ingestion-service**, **open-webui**.

### Конфигурация RAG (`.env`)

| Переменная | По умолчанию | Описание |
|------------|:------------:|----------|
| `RAG_ENABLED` | `true` | Включить RAG в `/v1/chat/completions` |
| `RAG_TOP_K` | `5` | Кол-во чанков после fusion |
| `RAG_BM25_K` | `5` | Top-k для BM25 |
| `RAG_BM25_MAX_DOCS` | `10000` | Макс. документов для BM25-корпуса |
| `RAG_HYBRID_ALPHA` | `0.5` | alpha·dense + (1−alpha)·BM25 |
| `RAG_RELEVANCE_THRESHOLD` | `0.0` | Мин. гибридный скор; ниже → отказ (0 = выкл.) |
| `RAG_QUERY_MAX_TURNS` | `3` | Сколько последних сообщений склеивать для запроса |
| `ENABLE_THINKING` | `true` | Включить reasoning (thinking) у LLM |

### Трассировка (LangSmith)

| Переменная | Описание |
|------------|----------|
| `LANGSMITH_TRACING` | `true` / `false` — включить трассировку |
| `LANGSMITH_API_KEY` | API-ключ LangSmith |
| `LANGSMITH_PROJECT` | Имя проекта в LangSmith |

### Тестирование API

После запуска:
- **Swagger UI**: http://localhost:8001/docs
- **Health**: `curl http://localhost:8001/api/health`
- **Chat**: `curl -X POST http://localhost:8001/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer $OPENROUTER_API_KEY" -d '{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"Привет!"}]}'`

---

## Сервисы

| Сервис | Порт | Описание |
|--------|:----:|----------|
| **ingestion-service** | 8001 | FastAPI: загрузка документов, RAG, OpenAI-совместимый API |
| **open-webui** | 3000 | Веб-чат, подключён к ingestion-service через `/v1` |
| **qdrant** | 6333 | Векторная БД |
| **postgres** | 5432 | История диалогов |
| **redis** | 6379 | Брокер задач Celery |
| **celery-worker** | — | Фоновая обработка документов |
| **telegram-bot** | — | Основной бот для студентов |
| **upload-bot** | — | Бот для админов: загрузка материалов |

### Веб-интерфейсы

- **Open WebUI** (чат) — http://localhost:3000
- **Qdrant Dashboard** — http://localhost:6333/dashboard
- **Swagger UI (Ingestion)** — http://localhost:8001/docs

---

## Дорожная карта

<details>
<summary><strong>Learning Agent</strong></summary>

- [x] RAG: объяснения и саммари
- [x] Настройка Qdrant и подключение
- [x] Пайплайн RAG: загрузка, чанкинг, эмбеддинги, индексация
- [x] Гибридный поиск (Dense + BM25) с порогом релевантности
- [x] LangSmith-трассировка RAG-пайплайна
- [x] История диалогов (PostgreSQL)
- [ ] Генерация тестов (`learning.quiz.generate`)
- [ ] Проверка тестов (`learning.quiz.grade`)
- [ ] План повторения (`learning.plan.revision`)

</details>

<details>
<summary><strong>Academic Agent</strong></summary>

- [ ] Профили преподавателей и требования к курсам
- [ ] Схема БД для академических данных
- [ ] Получение профиля преподавателя
- [ ] Получение требований к курсу

</details>

<details>
<summary><strong>Инфраструктура и интерфейсы</strong></summary>

- [x] Open WebUI
- [x] OpenAI-совместимый API (`/v1`)
- [x] Docker Compose (все сервисы)
- [x] PostgreSQL для хранения диалогов
- [x] LangSmith-трассировка
- [ ] Тесты и документация по развёртыванию

</details>

---

## Статус проекта

Проект в активной разработке. Список намерений и функциональность расширяются по мере развития.
