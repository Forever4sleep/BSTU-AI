"""Abstract query processor contract."""

from abc import ABC, abstractmethod
from typing import Any

Message = dict[str, Any]
Messages = list[Message]


class BaseQueryProcessor(ABC):
    """Transforms a raw user query before it reaches retrieval."""

    @abstractmethod
    def process(self, query: str, messages: Messages) -> str:
        """Return a retrieval-ready query string."""
