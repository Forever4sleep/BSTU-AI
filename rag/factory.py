"""RAGFactory — assembles RAG implementations from components via DI."""

from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient

from config import Config, get_config
from prompts import load_classified_rag_prompts
from rag.base import BaseRAG
from rag.implementation.classic import ClassicRAG
from rag.prompts.context_builder import ContextPromptBuilder
from rag.query.contextual import ContextualQueryProcessor
from rag.retrieval.bm25 import SparseBM25Retriever
from rag.retrieval.dense import DenseRetriever
from rag.retrieval.hybrid import HybridRetriever


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
            return cls._build_classic(qdrant_client, cfg)

        rag_class = cls._registry.get(name)
        if rag_class is not None:
            return rag_class(qdrant_client=qdrant_client, config=cfg)  # type: ignore[call-arg]

        available_types = [cls._CLASSIC_NAME, *cls._registry.keys()]
        raise ValueError(f"Unknown RAG type {name!r}. Available: {available_types}")

    @staticmethod
    def _build_classic(client: QdrantClient, cfg: Config) -> ClassicRAG:
        embedding = OpenAIEmbeddings(
            model=cfg.embedding_model,
            openai_api_key=cfg.embedding_api_key,
            openai_api_base=cfg.embedding_base_url_resolved,
            check_embedding_ctx_length=False,
        )

        dense = DenseRetriever(
            client,
            cfg.qdrant_collection_name,
            embedding,
            k=cfg.rag_top_k,
        )
        bm25 = SparseBM25Retriever(
            client,
            cfg.qdrant_collection_name,
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

        return ClassicRAG(
            retriever=retriever,
            query_processor=query_processor,
            prompt_builder=prompt_builder,
            relevance_threshold=cfg.rag_relevance_threshold,
            low_relevance_response=prompts.low_relevance_response,
            context_marker=prompts.context_marker,
        )
