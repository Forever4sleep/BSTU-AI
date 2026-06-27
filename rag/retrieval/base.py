"""Abstract retriever contract."""

from abc import ABC, abstractmethod

from langchain_core.documents import Document


class BaseRetriever(ABC):
    """All retrieval components implement this single method."""

    @abstractmethod
    def retrieve(self, query: str) -> list[Document]: ...
