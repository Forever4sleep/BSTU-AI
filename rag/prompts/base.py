"""Abstract prompt builder contract."""

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.documents import Document

Message = dict[str, Any]
Messages = list[Message]


class BasePromptBuilder(ABC):
    """Injects retrieved context into OpenAI-style chat messages."""

    @abstractmethod
    def inject(
        self,
        messages: Messages,
        docs: list[Document],
    ) -> str | None:
        """Inject retrieved docs into messages and return inserted system content."""
