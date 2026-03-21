"""No-op query processor — returns the query unchanged."""

from rag.query.base import BaseQueryProcessor, Messages


class PassthroughProcessor(BaseQueryProcessor):
    def process(self, query: str, messages: Messages) -> str:
        _ = messages
        return query
