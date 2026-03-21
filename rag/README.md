# RAG (`rag/`)

RAG через **dependency injection** и factory-паттерн.

## Использование

```python
from rag import RAGFactory

rag = RAGFactory.create("classic", qdrant_client=client)
rag.augment(messages)  # мутирует OpenAI-style messages in-place
```

## Добавление нового типа RAG (например, GraphRAG)

1. Наследуйтесь от `BaseRAG`, реализуйте `augment(messages)`.
2. Соберите из любой комбинации `BaseRetriever`, `BaseQueryProcessor`, `BasePromptBuilder` — или используйте свои компоненты.
3. Добавьте `_build_graph(...)` в `RAGFactory` или зарегистрируйте через `RAGFactory.register("graph", GraphRAG)`.

## Структура

```
rag/
├── base.py                          BaseRAG ABC + MessagePreprocessor
├── factory.py                       RAGFactory (реестр + DI-сборка)
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
        └── rag.py                   ClassicRAG (pure DI: retriever + query + prompts)
```

## Поток ClassicRAG

```
запрос пользователя
  → ContextualQueryProcessor (последние N сообщений)
  → HybridRetriever
      ├── DenseRetriever (Qdrant, косинусное сходство)
      └── SparseBM25Retriever (BM25 по корпусу из Qdrant)
      (fusion: alpha · dense + (1−alpha) · BM25, min-max нормализация)
  → ContextPromptBuilder (системное сообщение с фрагментами)
  → [порог релевантности: если лучший скор < threshold → отказ]
```

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
