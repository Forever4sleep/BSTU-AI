"""Sparse BM25 retrieval over a Qdrant collection."""

import logging
from collections.abc import Mapping

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
from qdrant_client import QdrantClient

from rag.retrieval.base import BaseRetriever

logger = logging.getLogger(__name__)


class SparseBM25Retriever(BaseRetriever):
    """
    Scrolls Qdrant payloads into a BM25 corpus (LangChain BM25Retriever).

    Rebuilds the corpus automatically when the collection size changes.
    """

    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        *,
        k: int = 5,
        max_docs: int = 10_000,
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._k = k
        self._max_docs = max_docs

        self._cached_count: int | None = None
        self._lc_bm25: BM25Retriever | None = None

    # ── corpus building ───────────────────────────────────────

    def _collection_count(self) -> int:
        count_result = self._client.count(
            collection_name=self._collection_name,
            exact=True,
        )
        return int(count_result.count)

    def _scroll_documents(self) -> list[Document]:
        docs: list[Document] = []
        offset = None
        while len(docs) < self._max_docs:
            batch, offset = self._client.scroll(
                collection_name=self._collection_name,
                limit=min(256, self._max_docs - len(docs)),
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in batch:
                pl = p.payload or {}
                text = pl.get("text")
                if not isinstance(text, str) or not text:
                    continue

                md_raw = pl.get("metadata")
                metadata = (
                    dict(md_raw)
                    if isinstance(md_raw, Mapping)
                    else {k: v for k, v in pl.items() if k != "text"}
                )
                docs.append(Document(page_content=text, metadata=metadata))
            if offset is None:
                break
        return docs

    def _ensure_bm25(self) -> BM25Retriever:
        count = self._collection_count()
        if self._lc_bm25 is not None and self._cached_count == count:
            return self._lc_bm25

        scroll_docs = self._scroll_documents()
        if not scroll_docs:
            logger.warning(
                "BM25: empty collection %r, returning no-op retriever",
                self._collection_name,
            )
            self._lc_bm25 = BM25Retriever.from_documents(
                [Document(page_content="")],
                k=self._k,
            )
        else:
            self._lc_bm25 = BM25Retriever.from_documents(scroll_docs, k=self._k)

        self._cached_count = count
        logger.debug("BM25: rebuilt corpus (count=%d, docs=%d)", count, len(scroll_docs))
        return self._lc_bm25

    # ── BaseRetriever contract ────────────────────────────────

    @traceable(run_type="retriever", name="bm25_retrieval")
    def retrieve(self, query: str) -> list[Document]:
        bm25 = self._ensure_bm25()
        docs = bm25.invoke(query)

        self._attach_scores(bm25, query, docs)

        return docs

    @staticmethod
    def _attach_scores(
        bm25: BM25Retriever, query: str, docs: list[Document],
    ) -> None:
        """Compute BM25 scores for returned docs and store in metadata."""
        if not docs or not hasattr(bm25, "vectorizer"):
            return

        tokenized = query.lower().split()
        all_scores = bm25.vectorizer.get_scores(tokenized)

        text_to_score: dict[str, float] = {}
        for i, corpus_doc in enumerate(bm25.docs):
            text_to_score[corpus_doc.page_content] = float(all_scores[i])

        trace_scores: list[dict[str, str | float]] = []
        for doc in docs:
            score = text_to_score.get(doc.page_content, 0.0)
            doc.metadata["retrieval_score"] = score
            trace_scores.append({
                "content_preview": doc.page_content[:80],
                "score": round(score, 4),
            })

        trace_scores.sort(key=lambda s: s["score"], reverse=True)

        try:
            run_tree = get_current_run_tree()
            if run_tree is not None:
                run_tree.metadata["bm25_scores"] = trace_scores
        except Exception:
            pass
