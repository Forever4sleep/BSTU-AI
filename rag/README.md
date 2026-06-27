# RAG (`rag/`)

Библиотека retrieval-augmented generation с **dependency injection** и factory-паттерном. Используется Ingestion Service в `/v1/chat/completions`, чате платформы по курсу и при подготовке контекста для AI-черновиков задач.

---

## Использование

### Глобальная коллекция (legacy / Open WebUI)

```python
from rag import RAGFactory

rag = RAGFactory.create("classic", qdrant_client=client)
rag.augment(messages)  # мутирует OpenAI-style messages in-place
```

### Per-course коллекция (чат платформы)

```python
rag = RAGFactory.classic_for_collection(
    client,
    collection_name="course_algorithms",
    course_slug="algorithms",
    anti_cheat_mode="advanced",  # off | basic | advanced
)
rag.augment(messages)
```

`classic_for_collection` кэширует экземпляры по ключу `(collection, slug, anti_cheat_mode)`.

---

## Поток ClassicRAG

```
запрос пользователя
  → ContextualQueryProcessor (последние N сообщений)
  → [если course_slug + anti_cheat ≠ off]
      Agent Checker (LangGraph) — блокировка подсказок по заданиям
      [режим basic: cosine-сходство запроса с условиями задач в Qdrant]
  → HybridRetriever
      ├── DenseRetriever (Qdrant, косинусное сходство)
      └── SparseBM25Retriever (BM25 по корпусу из Qdrant)
      (fusion: alpha · dense + (1−alpha) · BM25, min-max нормализация)
  → ContextPromptBuilder (системное сообщение с фрагментами из prompts/classified_rag.yaml)
  → [порог релевантности: если лучший скор < threshold → отказ без LLM]
```

Промпты загружаются из `prompts/classified_rag.yaml` через `prompts.load_classified_rag_prompts()`.

---

## Структура

```
rag/
├── base.py                          BaseRAG ABC + MessagePreprocessor
├── factory.py                       RAGFactory (реестр + DI + per-collection cache)
├── retrieval/
│   ├── base.py                      BaseRetriever ABC
│   ├── dense.py                     DenseRetriever (QdrantVectorStore, косинус)
│   ├── bm25.py                      SparseBM25Retriever (BM25 по корпусу из Qdrant)
│   └── hybrid.py                    HybridRetriever (alpha·dense + (1−alpha)·BM25)
├── query/
│   ├── base.py                      BaseQueryProcessor ABC
│   ├── passthrough.py               PassthroughProcessor (identity)
│   ├── contextual.py                ContextualQueryProcessor (склейка последних сообщений)
│   └── classifier.py                ClassifierProcessor (route enum, заглушка)
├── prompts/
│   ├── base.py                      BasePromptBuilder ABC
│   └── context_builder.py           ContextPromptBuilder (системное сообщение из фрагментов)
└── implementation/
    └── classic/
        └── rag.py                   ClassicRAG (retriever + query + prompts + anti-cheat)
```

---

## Qdrant-коллекции

| Коллекция | Назначение |
|-----------|------------|
| `bstu_materials` (config) | Глобальные материалы (upload bot, legacy) |
| `course_<slug>` | Материалы конкретного курса платформы |
| `course_<slug>_problems` | Опубликованные условия задач (античит, basic mode) |

Именование — в `services/ingestion_service/problem_platform/qdrant_naming.py`.

---

## Добавление нового типа RAG (например, GraphRAG)

1. Наследуйтесь от `BaseRAG`, реализуйте `augment(messages)`.
2. Соберите из любой комбинации `BaseRetriever`, `BaseQueryProcessor`, `BasePromptBuilder` — или используйте свои компоненты.
3. Зарегистрируйте: `RAGFactory.register("graph", GraphRAG)` или добавьте `_build_graph(...)` в factory.

---

## Конфигурация (`.env`)

| Переменная | По умолчанию | Описание |
|------------|:------------:|----------|
| `RAG_ENABLED` | `true` | Вкл./выкл. RAG в `/v1/chat/completions` |
| `RAG_TOP_K` | `5` | Чанков после fusion |
| `RAG_BM25_K` | `5` | Top-k для BM25 |
| `RAG_BM25_MAX_DOCS` | `10000` | Макс. документов для BM25-корпуса |
| `RAG_HYBRID_ALPHA` | `0.5` | alpha·dense + (1−alpha)·BM25 |
| `RAG_RELEVANCE_THRESHOLD` | `0.0` | Мин. гибридный скор; ниже → отказ (0 = выкл.) |
| `RAG_QUERY_MAX_TURNS` | `3` | Кол-во последних сообщений для retrieval-запроса |
| `RAG_PROBLEM_MATCH_ENABLED` | `true` | Включить античит для course chat |
| `RAG_PROBLEM_MATCH_THRESHOLD` | `0.82` | Cosine-порог для режима `basic` (0..1) |

Режим античита на уровне курса (`off` / `basic` / `advanced`) задаётся в настройках курса платформы и передаётся в `classic_for_collection`.

---

## Наблюдаемость

При `LANGSMITH_TRACING=true` пайплайн трассируется в LangSmith: запрос, история, чанки, скоры (dense, BM25, hybrid), ответ LLM. Ingestion Service вызывает `langsmith.Client().flush()` при shutdown.
