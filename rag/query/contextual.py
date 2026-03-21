"""Contextual query processor — concatenates recent user turns for multi-turn retrieval."""

from langsmith import traceable

from rag.base import MessagePreprocessor
from rag.query.base import BaseQueryProcessor, Messages


class ContextualQueryProcessor(BaseQueryProcessor):
    """
    Builds a retrieval query from the last N user messages.

    Handles "tell me more about that" style follow-ups by giving the
    retriever enough conversational context without an LLM reformulation step.
    """

    def __init__(self, max_turns: int = 3) -> None:
        self._max_turns = max_turns

    @traceable(name="query_processing")
    def process(self, query: str, messages: Messages) -> str:
        user_texts: list[str] = []
        for chat_message in messages:
            if chat_message.get("role") != "user":
                continue

            text = MessagePreprocessor.extract_text(chat_message.get("content")).strip()
            if text:
                user_texts.append(text)

        recent = user_texts[-self._max_turns :]
        if not recent:
            return query

        return "\n".join(recent)
