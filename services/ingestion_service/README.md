# Ingestion Service

> **Сервис загрузки и индексации документов для RAG**

FastAPI-микросервис для приёма документов, их обработки и индексации в Qdrant. Формирует векторное хранилище для RAG-пайплайнов.

---

## Пайплайн обработки

```
Документ (PDF/DOCX/TXT) → Парсинг → Чанкинг → Эмбеддинги → Qdrant
```

1. **Парсинг** — извлечение текста из PDF, DOCX, TXT  
2. **Чанкинг** — разбиение на фрагменты с перекрытием (500 символов, overlap 50)  
3. **Эмбеддинги** — векторизация через OpenRouter (OpenAI-совместимый API)  
4. **Индексация** — upsert в Qdrant с метаданными  

---

## Конфигурация

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `QDRANT_HOST` | Хост Qdrant | `localhost` |
| `QDRANT_PORT` | Порт Qdrant | `6333` |
| `QDRANT_COLLECTION_NAME` | Имя коллекции | `bstu_materials` |
| `INGESTION_SERVICE_PORT` | Порт API | `8001` |
| `OPENROUTER_API_KEY` | API-ключ для эмбеддингов | *обязательно* |
| `EMBEDDING_MODEL` | Модель эмбеддингов | `openai/text-embedding-3-small` |
| `EMBEDDING_BASE_URL` | URL API эмбеддингов | `https://openrouter.ai/api/v1` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |

---

## API

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/upload` | Загрузка документа (multipart/form-data) |
| `GET` | `/api/health` | Проверка здоровья (подключение к Qdrant) |
| `GET` | `/api/collections` | Список коллекций Qdrant |
| `GET` | `/api/subjects` | Список уникальных предметов в коллекции |

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
