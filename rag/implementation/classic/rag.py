"""ClassicRAG — hybrid BM25 + dense retrieval, composed via dependency injection."""

import logging
from typing import Any

from langsmith import traceable

from rag.base import BaseRAG, MessagePreprocessor
from rag.prompts.base import BasePromptBuilder
from rag.query.base import BaseQueryProcessor
from rag.retrieval.base import BaseRetriever

logger = logging.getLogger(__name__)


class ClassicRAG(BaseRAG):
    """
    Pure DI: knows nothing about Qdrant, BM25, LangChain, or YAML prompts.

    All behaviour is injected via the three constructor arguments.
    """

    def __init__(
        self,
        *,
        retriever: BaseRetriever,
        query_processor: BaseQueryProcessor,
        prompt_builder: BasePromptBuilder,
        relevance_threshold: float = 0.0,
        low_relevance_response: str = "К сожалению, я не могу ответить на ваш запрос.",
        context_marker: str = "",
    ) -> None:
        self._retriever = retriever
        self._query_processor = query_processor
        self._prompt_builder = prompt_builder
        self._relevance_threshold = relevance_threshold
        self._low_relevance_response = low_relevance_response
        self._context_marker = context_marker

    @traceable(name="rag_augment")
    def augment(self, messages: list[dict[str, Any]]) -> None:
        query = MessagePreprocessor.last_user_query(messages)
        if not query:
            logger.debug("ClassicRAG: no user query, skipping")
            return

        processed = self._query_processor.process(query, messages)
        docs = self._retriever.retrieve(processed)

        if self._relevance_threshold > 0 and docs:
            best_score = max(d.metadata.get("hybrid_score", 0.0) for d in docs)
            if best_score < self._relevance_threshold:
                logger.info(
                    "ClassicRAG: best hybrid score %.4f < threshold %.4f — refusing",
                    best_score,
                    self._relevance_threshold,
                )
                if self._context_marker:
                    MessagePreprocessor.strip_system_by_marker(
                        messages,
                        self._context_marker,
                    )
                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": (
                            "Пользователь задал вопрос, но релевантных данных не найдено. "
                            "Ответь ровно следующей фразой, без дополнений:\n"
                            f"{self._low_relevance_response}"
                        ),
                    },
                )
                return

        self._prompt_builder.inject(messages, docs)

        preview_len = 120
        query_preview = processed[:preview_len] + (
            "…" if len(processed) > preview_len else ""
        )
        logger.info(
            "ClassicRAG: query=%r hits=%d",
            query_preview,
            len(docs),
        )
