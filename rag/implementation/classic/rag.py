"""ClassicRAG — hybrid BM25 + dense retrieval, composed via dependency injection."""

import logging
from typing import Any, Literal

from langsmith import traceable
from qdrant_client import QdrantClient

from rag.base import BaseRAG, MessagePreprocessor
from rag.prompts.base import BasePromptBuilder
from rag.query.base import BaseQueryProcessor
from rag.retrieval.base import BaseRetriever
from services.ingestion_service.problem_platform.graphs.agent_checker_graph import run_agent_checker_sync
from services.ingestion_service.problem_platform.problem_qdrant import (
    find_similar_problem,
    scroll_course_problems,
)

logger = logging.getLogger(__name__)

AntiCheatMode = Literal["off", "basic", "advanced"]


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
        qdrant_client: QdrantClient | None = None,
        problems_collection: str = "",
        course_slug: str = "",
        anti_cheat_mode: AntiCheatMode = "off",
        agent_checker_max_messages: int = 12,
        problem_match_threshold: float = 0.82,
    ) -> None:
        self._retriever = retriever
        self._query_processor = query_processor
        self._prompt_builder = prompt_builder
        self._relevance_threshold = relevance_threshold
        self._low_relevance_response = low_relevance_response
        self._context_marker = context_marker
        self._qdrant_client = qdrant_client
        self._problems_collection = problems_collection.strip()
        self._course_slug = course_slug.strip().lower()
        self._anti_cheat_mode = anti_cheat_mode
        self._agent_checker_max_messages = max(2, agent_checker_max_messages)
        self._problem_match_threshold = problem_match_threshold

    def _anti_cheat_match(self, messages: list[dict[str, Any]]) -> dict[str, Any] | None:
        if self._anti_cheat_mode == "off":
            return None
        if not (self._problems_collection and self._qdrant_client):
            return None
        query = MessagePreprocessor.last_user_query(messages)
        if not query:
            return None

        if self._anti_cheat_mode == "basic":
            try:
                hit = find_similar_problem(
                    self._qdrant_client,
                    self._problems_collection,
                    query,
                    threshold=self._problem_match_threshold,
                )
            except Exception:
                logger.warning("ClassicRAG: basic anti-cheat failed — fail open", exc_info=True)
                return None
            if hit:
                return {
                    "problem_id": hit["problem_id"],
                    "title": hit["title"],
                    "reasoning": f"similarity={hit.get('score', 0):.3f}",
                }
            return None

        return self._run_agent_checker(messages, query)

    def _run_agent_checker(
        self,
        messages: list[dict[str, Any]],
        query: str,
    ) -> dict[str, Any] | None:
        chat_transcript = MessagePreprocessor.dialogue_transcript(
            messages,
            max_messages=self._agent_checker_max_messages,
        )
        try:
            problems = scroll_course_problems(self._qdrant_client, self._problems_collection)
        except Exception:
            logger.warning(
                "ClassicRAG: failed to scroll problems collection %s",
                self._problems_collection,
                exc_info=True,
            )
            return None
        if not problems:
            return None
        try:
            verdict = run_agent_checker_sync(
                user_query=query,
                chat_transcript=chat_transcript,
                problems=problems,
            )
        except Exception:
            logger.warning("ClassicRAG: Agent Checker failed — fail open to RAG", exc_info=True)
            return None
        if verdict.allow_rag:
            logger.info("ClassicRAG: Agent Checker allow_rag — %s", verdict.reasoning[:200])
            return None
        problem_id = (verdict.matched_problem_id or "").strip()
        if not problem_id:
            logger.info(
                "ClassicRAG: Agent Checker blocked but no problem_id — fail open: %s",
                verdict.reasoning[:200],
            )
            return None
        title = (verdict.matched_title or "").strip()
        if not title:
            for p in problems:
                if p.get("problem_id") == problem_id:
                    title = str(p.get("title") or "")
                    break
        return {
            "problem_id": problem_id,
            "title": title or "задание курса",
            "reasoning": verdict.reasoning,
        }

    def _inject_problem_match_refusal(self, messages: list[dict[str, Any]], match: dict[str, Any]) -> None:
        title = match["title"]
        problem_id = match["problem_id"]
        slug = self._course_slug or "course"
        problem_path = f"/c/{slug}/p/{problem_id}"
        response = (
            f"Похоже, ваш вопрос совпадает с заданием курса «{title}».\n"
            f"[Перейти к заданию]({problem_path})\n\n"
            "Я не могу выдавать готовое решение заданий в чате — попробуйте решить "
            "самостоятельно или задайте общий вопрос по материалам курса."
        )
        if self._context_marker:
            MessagePreprocessor.strip_system_by_marker(messages, self._context_marker)
        messages.insert(
            0,
            {
                "role": "system",
                "content": (
                    "Пользователь задал вопрос, совпадающий с заданием курса. "
                    "Ответь ровно следующим текстом, без дополнений:\n"
                    f"{response}"
                ),
            },
        )

    @traceable(name="rag_augment")
    def augment(self, messages: list[dict[str, Any]]) -> None:
        query = MessagePreprocessor.last_user_query(messages)
        if not query:
            logger.debug("ClassicRAG: no user query, skipping")
            return

        match = self._anti_cheat_match(messages)
        if match:
            logger.info(
                "ClassicRAG: anti-cheat block (%s) problem_id=%s — refusing lecture RAG",
                self._anti_cheat_mode,
                match["problem_id"],
            )
            self._inject_problem_match_refusal(messages, match)
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
