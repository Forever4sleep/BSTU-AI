"""RAGFactory — assembles RAG implementations from components via DI."""

import threading

from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient

from config import Config, get_config
from prompts import load_classified_rag_prompts
from services.ingestion_service.problem_platform.qdrant_naming import course_problems_collection_from_slug
from rag.base import BaseRAG
from rag.implementation.classic import ClassicRAG
from rag.prompts.context_builder import ContextPromptBuilder
from rag.query.contextual import ContextualQueryProcessor
from rag.retrieval.bm25 import SparseBM25Retriever
from rag.retrieval.dense import DenseRetriever
from rag.retrieval.hybrid import HybridRetriever

_classic_by_collection: dict[str, ClassicRAG] = {}
_classic_lock = threading.Lock()


class RAGFactory:
    """
    Registry + builder for RAG implementations.

    Built-in: "classic" (hybrid BM25 + dense).
    Extend:   RAGFactory.register("graph", build_graph_rag)
    """

    _registry: dict[str, type[BaseRAG]] = {}
    _CLASSIC_NAME = "classic"

    @classmethod
    def register(cls, name: str, rag_class: type[BaseRAG]) -> None:
        cls._registry[name] = rag_class

    @classmethod
    def create(
        cls,
        name: str,
        *,
        qdrant_client: QdrantClient,
        config: Config | None = None,
    ) -> BaseRAG:
        cfg = config or get_config()

        if name == cls._CLASSIC_NAME:
            return cls._build_classic(qdrant_client, cfg, collection_name=None)

        rag_class = cls._registry.get(name)
        if rag_class is not None:
            return rag_class(qdrant_client=qdrant_client, config=cfg)  # type: ignore[call-arg]

        available_types = [cls._CLASSIC_NAME, *cls._registry.keys()]
        raise ValueError(f"Unknown RAG type {name!r}. Available: {available_types}")

    @classmethod
    def classic_for_collection(
        cls,
        client: QdrantClient,
        collection_name: str,
        cfg: Config | None = None,
        *,
        course_slug: str | None = None,
        anti_cheat_mode: str = "off",
    ) -> ClassicRAG:
        """Один ClassicRAG на имя коллекции + slug + режим античита (кэш; для чата по курсу)."""
        cfg = cfg or get_config()
        if not collection_name.strip():
            return cls._build_classic(client, cfg, collection_name=None)
        slug = (course_slug or "").strip().lower()
        mode = cls._effective_anti_cheat_mode(cfg, anti_cheat_mode, bool(slug))
        key = f"{collection_name.strip()}:{slug}:{mode}"
        with _classic_lock:
            hit = _classic_by_collection.get(key)
            if hit is not None:
                return hit
            inst = cls._build_classic(
                client,
                cfg,
                collection_name=collection_name.strip(),
                course_slug=slug or None,
                anti_cheat_mode=mode,
            )
            _classic_by_collection[key] = inst
            return inst

    @staticmethod
    def _effective_anti_cheat_mode(cfg: Config, course_mode: str, has_slug: bool) -> str:
        if not cfg.rag_problem_match_enabled or not has_slug:
            return "off"
        v = (course_mode or "advanced").strip().lower()
        if v in ("off", "basic", "advanced"):
            return v
        return "advanced"

    @staticmethod
    def _build_classic(
        client: QdrantClient,
        cfg: Config,
        collection_name: str | None,
        course_slug: str | None = None,
        anti_cheat_mode: str = "off",
    ) -> ClassicRAG:
        cn = (collection_name or "").strip() or cfg.qdrant_collection_name
        slug = (course_slug or "").strip().lower()
        embedding = OpenAIEmbeddings(
            model=cfg.embedding_model,
            openai_api_key=cfg.embedding_api_key,
            openai_api_base=cfg.embedding_base_url_resolved,
            check_embedding_ctx_length=False,
        )

        dense = DenseRetriever(
            client,
            cn,
            embedding,
            k=cfg.rag_top_k,
        )
        bm25 = SparseBM25Retriever(
            client,
            cn,
            k=cfg.rag_bm25_k,
            max_docs=cfg.rag_bm25_max_docs,
        )
        alpha = cfg.rag_hybrid_alpha
        retriever = HybridRetriever(
            retrievers=[dense, bm25],
            weights=[alpha, 1.0 - alpha],
            top_k=cfg.rag_top_k,
            retriever_names=["dense", "bm25"],
        )

        query_processor = ContextualQueryProcessor(max_turns=cfg.rag_query_max_turns)
        prompts = load_classified_rag_prompts()
        prompt_builder = ContextPromptBuilder(prompts)

        problems_collection = course_problems_collection_from_slug(slug) if slug else ""
        checker_context = min(20, max(6, cfg.rag_query_max_turns * 4))

        return ClassicRAG(
            retriever=retriever,
            query_processor=query_processor,
            prompt_builder=prompt_builder,
            relevance_threshold=cfg.rag_relevance_threshold,
            low_relevance_response=prompts.low_relevance_response,
            context_marker=prompts.context_marker,
            qdrant_client=client if slug else None,
            problems_collection=problems_collection,
            course_slug=slug,
            anti_cheat_mode=anti_cheat_mode if anti_cheat_mode in ("off", "basic", "advanced") else "off",  # type: ignore[arg-type]
            agent_checker_max_messages=checker_context,
            problem_match_threshold=cfg.rag_problem_match_threshold,
        )
