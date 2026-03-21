"""
RAG — pluggable retrieval-augmented generation via dependency injection.

Usage:
    rag = RAGFactory.create("classic", qdrant_client=client)
    rag.augment(messages)
"""

from rag.base import BaseRAG, MessagePreprocessor
from rag.factory import RAGFactory

__all__ = [
    "BaseRAG",
    "MessagePreprocessor",
    "RAGFactory",
]
