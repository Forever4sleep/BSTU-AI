"""Dense vector retrieval via Qdrant."""

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
from qdrant_client import QdrantClient

from rag.retrieval.base import BaseRetriever


class DenseRetriever(BaseRetriever):
    """Wraps LangChain QdrantVectorStore for cosine-similarity search."""

    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        embedding: Embeddings,
        *,
        k: int = 5,
    ) -> None:
        self._store = QdrantVectorStore(
            client=client,
            collection_name=collection_name,
            embedding=embedding,
            content_payload_key="text",
            metadata_payload_key="metadata",
            validate_collection_config=False,
        )
        self._k = k

    @traceable(run_type="retriever", name="dense_retrieval")
    def retrieve(self, query: str) -> list[Document]:
        results_with_scores = self._store.similarity_search_with_score(query, k=self._k)

        docs: list[Document] = []
        trace_scores: list[dict[str, str | float]] = []
        for doc, score in results_with_scores:
            doc.metadata["retrieval_score"] = float(score)
            docs.append(doc)
            trace_scores.append({
                "content_preview": doc.page_content[:80],
                "score": round(float(score), 4),
            })

        try:
            run_tree = get_current_run_tree()
            if run_tree is not None:
                run_tree.metadata["dense_scores"] = trace_scores
        except Exception:
            pass

        return docs
