"""Builds a system message from retrieved excerpts and injects it into the chat."""

from typing import Any

from langchain_core.documents import Document
from langsmith import traceable

from prompts import ClassifiedRAGPromptTemplate
from rag.base import MessagePreprocessor
from rag.prompts.base import BasePromptBuilder


class ContextPromptBuilder(BasePromptBuilder):
    """
    Strips prior RAG system messages (by marker), formats retrieved docs,
    and prepends a fresh system message using the YAML prompt template.
    """

    def __init__(self, template: ClassifiedRAGPromptTemplate) -> None:
        self._template = template

    @staticmethod
    def _format_context(docs: list[Document]) -> str:
        blocks: list[str] = []
        for index, doc in enumerate(docs, start=1):
            source = doc.metadata.get("source_file", "?")
            blocks.append(f"[{index}] (source: {source})\n{doc.page_content}")
        return "\n\n---\n\n".join(blocks)

    @traceable(name="prompt_injection")
    def inject(self, messages: list[dict[str, Any]], docs: list[Document]) -> str:
        MessagePreprocessor.strip_system_by_marker(messages, self._template.context_marker)

        context_str = self._format_context(docs)
        system_content = self._template.build_system_content(
            context_str,
            had_hits=bool(docs),
        )
        messages.insert(0, {"role": "system", "content": system_content})
        return system_content
