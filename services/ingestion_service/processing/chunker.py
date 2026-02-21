"""
Text Chunker

Uses LangChain's RecursiveCharacterTextSplitter for structure-aware chunking.
Splits on paragraph, line, space boundaries before falling back to character-level.
"""

import logging
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[str]:
    """
    Split text into overlapping chunks using recursive character splitting.

    Tries separators in order: paragraph breaks, newlines, spaces, then characters.
    Keeps semantic coherence for learning materials (lectures, lab guides).

    Args:
        text: Input text to chunk
        chunk_size: Maximum chunk size in characters
        chunk_overlap: Overlap between consecutive chunks

    Returns:
        List of text chunks
    """
    if not text or not text.strip():
        logger.warning("Chunking skipped: empty or whitespace-only text")
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_text(text.strip())

    logger.info(
        f"Chunked text into {len(chunks)} chunks (chunk_size={chunk_size}, overlap={chunk_overlap})"
    )
    return chunks
