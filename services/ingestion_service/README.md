# API Service (Ingestion + OpenAI Proxy)

> **Загрузка документов, RAG-индексация и OpenAI-совместимый прокси для OpenWebUI**

FastAPI-сервис: приём документов, sliding window chunking, индексация в Qdrant, проксирование LLM-запросов в OpenRouter.

---

## Пайплайн обработки документов

```
Документ (PDF/DOCX/TXT) → Парсинг → Sliding Window Chunking → Эмбеддинги → Qdrant
```

1. **Парсинг** — извлечение текста из PDF, DOCX, TXT  
2. **Sliding Window Chunking** — разбиение с перекрытием (chunk_size, chunk_overlap)  
3. **Эмбеддинги** — векторизация через OpenRouter  
4. **Индексация** — upsert в Qdrant с метаданными  

---

## Конфигурация

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `QDRANT_HOST` | Хост Qdrant | `localhost` |
| `QDRANT_PORT` | Порт Qdrant | `6333` |
| `QDRANT_COLLECTION_NAME` | Имя коллекции | `bstu_materials` |
| `INGESTION_SERVICE_PORT` | Порт API | `8001` |
| `CHUNK_SIZE` | Размер чанка (символы) | `500` |
| `CHUNK_OVERLAP` | Перекрытие между чанками | `50` |
| `OPENROUTER_API_KEY` | API-ключ (эмбеддинги + LLM) | *обязательно* |
| `EMBEDDING_MODEL` | Модель эмбеддингов | `openai/text-embedding-3-small` |
| `OPENROUTER_MODEL` | Модель LLM (для /v1) | `openai/gpt-4o-mini` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |

---

## API

### Документы

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/upload` | Загрузка одного документа |
| `POST` | `/api/upload/batch` | Пакетная загрузка документов |
| `GET` | `/api/health` | Проверка здоровья |
| `GET` | `/api/collections` | Список коллекций Qdrant |
| `GET` | `/api/subjects` | Список предметов в коллекции |

### OpenAI-совместимые (для OpenWebUI)

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/v1/models` | Список моделей |
| `POST` | `/v1/chat/completions` | Chat completions (streaming и non-streaming) |
| `POST` | `/v1/completions` | Legacy completions |

---

## Запуск

```bash
python -m services.ingestion_service.main
```

С uvicorn:

```bash
uvicorn services.ingestion_service.main:app --host 0.0.0.0 --port 8001
```

---

## Зависимости

- FastAPI, uvicorn  
- qdrant-client  
- pypdf, python-docx  
- httpx (для эмбеддингов)
