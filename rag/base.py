"""Abstract RAG contract and shared message helpers."""

from abc import ABC, abstractmethod
from typing import Any, MutableSequence


class BaseRAG(ABC):
    """
    Common contract for all RAG implementations (ClassifiedRAG, GraphRAG, …).

    Implementations mutate ``messages`` in place:
    strip prior injections → retrieve → inject fresh system message.
    """

    @abstractmethod
    def augment(self, messages: list[dict[str, Any]]) -> None:
        """Retrieve context and inject it into OpenAI-style chat messages."""


class MessagePreprocessor:
    """Utilities for parsing OpenAI / Open WebUI chat message lists."""

    @staticmethod
    def extract_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text", "")))
            return "\n".join(p for p in parts if p)
        return str(content) if content is not None else ""

    @classmethod
    def last_user_query(cls, messages: list[dict[str, Any]]) -> str | None:
        for m in reversed(messages):
            if m.get("role") != "user":
                continue
            text = cls.extract_text(m.get("content"))
            if text.strip():
                return text.strip()
        return None

    @classmethod
    def dialogue_transcript(
        cls,
        messages: list[dict[str, Any]],
        *,
        max_messages: int = 12,
    ) -> str:
        """Recent user/assistant turns for Agent Checker (excludes system)."""
        lines: list[str] = []
        for m in messages:
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            text = cls.extract_text(m.get("content")).strip()
            if not text:
                continue
            label = "Студент" if role == "user" else "Ассистент"
            lines.append(f"{label}: {text}")
        if max_messages > 0:
            lines = lines[-max_messages:]
        return "\n\n".join(lines)

    @classmethod
    def strip_system_by_marker(
        cls,
        messages: MutableSequence[dict[str, Any]],
        marker: str,
    ) -> None:
        i = 0
        while i < len(messages):
            message = messages[i]
            if message.get("role") != "system":
                i += 1
                continue
            content = message.get("content")
            if isinstance(content, str) and content.startswith(marker):
                del messages[i]
                continue
            i += 1
