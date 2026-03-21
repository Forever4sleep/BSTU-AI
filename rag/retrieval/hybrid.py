"""Hybrid retriever — weighted linear combination of normalized retriever scores."""

import logging
from collections import defaultdict

from langchain_core.documents import Document
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

from rag.retrieval.base import BaseRetriever

logger = logging.getLogger(__name__)


def _min_max_normalize(scores: dict[str, float]) -> dict[str, float]:
    """Scale values to [0, 1].  All-equal → 1.0 for every key."""
    if not scores:
        return {}
    lo, hi = min(scores.values()), max(scores.values())
    rng = hi - lo
    if rng == 0:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / rng for k, v in scores.items()}


class HybridRetriever(BaseRetriever):
    """
    Weighted linear combination over N BaseRetrievers.

    Each sub-retriever must store ``doc.metadata["retrieval_score"]``.
    Scores are min-max normalised per retriever, then combined as::

        score(d) = Σ  weight_i · norm_score_i(d)

    For two retrievers with weights ``[alpha, 1-alpha]`` this gives the
    classic ``alpha·dense + (1−alpha)·bm25`` formula.
    """

    def __init__(
        self,
        retrievers: list[BaseRetriever],
        weights: list[float],
        *,
        top_k: int = 5,
        retriever_names: list[str] | None = None,
    ) -> None:
        if len(retrievers) != len(weights):
            raise ValueError("len(retrievers) must equal len(weights)")
        if not any(w > 0 for w in weights):
            raise ValueError("At least one weight must be > 0")

        self._retrievers = retrievers
        self._weights = weights
        self._top_k = top_k
        self._retriever_names = retriever_names or [
            type(r).__name__ for r in retrievers
        ]

    @traceable(run_type="retriever", name="hybrid_retrieval")
    def retrieve(self, query: str) -> list[Document]:
        per_retriever: list[list[Document]] = []
        for retriever in self._retrievers:
            try:
                per_retriever.append(retriever.retrieve(query))
            except Exception:
                logger.exception("HybridRetriever: sub-retriever failed, skipping")
                per_retriever.append([])

        doc_map: dict[str, Document] = {}
        raw_scores: list[dict[str, float]] = [{} for _ in self._retrievers]

        for i, docs in enumerate(per_retriever):
            for doc in docs:
                key = doc.page_content
                if key not in doc_map:
                    doc_map[key] = doc
                raw_scores[i][key] = doc.metadata.get("retrieval_score", 0.0)

        norm_scores = [_min_max_normalize(s) for s in raw_scores]

        combined: dict[str, float] = defaultdict(float)
        for weight, scores in zip(self._weights, norm_scores):
            for key, score in scores.items():
                combined[key] += weight * score

        sorted_keys = sorted(combined, key=combined.get, reverse=True)
        result: list[Document] = []
        for key in sorted_keys[: self._top_k]:
            doc = doc_map[key]
            doc.metadata["hybrid_score"] = round(combined[key], 6)
            result.append(doc)

        try:
            run_tree = get_current_run_tree()
            if run_tree is not None:
                run_tree.metadata.update({
                    "retriever_names": self._retriever_names,
                    "weights": self._weights,
                    "top_k": self._top_k,
                    "hybrid_scores": {
                        key[:80]: round(combined[key], 6)
                        for key in sorted_keys[: self._top_k]
                    },
                })
        except Exception:
            pass

        return result
