"""
Text Chunker

Strategy pattern for text chunking (ref: refactoring.guru/design-patterns/strategy).
"""

import logging
from abc import ABC, abstractmethod
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class ChunkerStrategy(ABC):
    """
    The Strategy interface declares operations common to all chunking algorithms.

    The Context (DocumentIndexer) uses this interface to call the algorithm
    defined by Concrete Strategies.
    """

    @abstractmethod
    def chunk(self, text: str) -> List[str]:
        """Split text into chunks. Returns list of strings."""
        pass


def _check_empty(text: str) -> bool:
    """Return True if text is empty (skip chunking)."""
    if not text or not text.strip():
        logger.warning("Chunking skipped: empty or whitespace-only text")
        return True
    return False


class SlidingWindowChunker(ChunkerStrategy):
    """
    Concrete strategy: sliding window with overlap.

    Slides a fixed-size window over the text. Each chunk overlaps with the
    previous by chunk_overlap characters.
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be less than chunk_size ({chunk_size})"
            )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._step = chunk_size - chunk_overlap

    def chunk(self, text: str) -> List[str]:
        if _check_empty(text):
            return []
        text = text.strip()
        if len(text) <= self.chunk_size:
            return [text]

        chunks: List[str] = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start += self._step
            if end >= len(text):
                break

        logger.info(
            f"SlidingWindowChunker: {len(chunks)} chunks "
            f"(size={self.chunk_size}, overlap={self.chunk_overlap})"
        )
        return chunks


class RecursiveChunker(ChunkerStrategy):
    """
    Concrete strategy: recursive character splitter (LangChain).

    Splits on paragraph, newline, space boundaries first for semantic coherence.
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be less than chunk_size ({chunk_size})"
            )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""],
        )

    def chunk(self, text: str) -> List[str]:
        if _check_empty(text):
            return []
        chunks = self._splitter.split_text(text.strip())
        logger.info(
            f"RecursiveChunker: {len(chunks)} chunks "
            f"(size={self.chunk_size}, overlap={self.chunk_overlap})"
        )
        return chunks


def create_chunker(
    strategy: str = "sliding_window",
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> ChunkerStrategy:
    """Create a concrete chunker strategy by name."""
    if strategy == "sliding_window":
        return SlidingWindowChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if strategy == "recursive":
        return RecursiveChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    raise ValueError(f"Unknown chunking strategy: {strategy}")
