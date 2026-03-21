"""Query classifier — routes queries by type (extensible)."""

import logging
from enum import Enum

from rag.query.base import BaseQueryProcessor, Messages

logger = logging.getLogger(__name__)


class QueryRoute(str, Enum):
    """Add values here for multi-collection or topic-based routing."""

    GENERAL = "general"


class ClassifierProcessor(BaseQueryProcessor):
    """
    Stub — always returns the query unchanged and logs GENERAL route.

    Swap for a real classifier (LLM-based, keyword, etc.) when needed.
    The route can be used downstream by retriever or prompt builder.
    """

    def __init__(self) -> None:
        self._route: QueryRoute = QueryRoute.GENERAL

    @property
    def last_route(self) -> QueryRoute:
        return self._route

    def process(self, query: str, messages: Messages) -> str:
        _ = messages
        self._route = self._classify(query)
        logger.debug("QueryClassifier: route=%s", self._route.value)
        return query

    def _classify(self, query: str) -> QueryRoute:
        _ = query
        return QueryRoute.GENERAL
