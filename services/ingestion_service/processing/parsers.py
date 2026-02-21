"""
Document Parsers

Extract text from PDF, DOCX, and TXT files.
"""

import logging
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


def parse_document(file_path: Path) -> str:
    """
    Parse a document and extract text based on file extension.

    Args:
        file_path: Path to the document file

    Returns:
        Extracted text content

    Raises:
        ValueError: If file format is not supported
    """
    suffix = file_path.suffix.lower()
    if suffix == ".doc":
        suffix = ".docx"

    logger.info(f"Parsing document: {file_path.name}, format={suffix}")

    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: {suffix}. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    try:
        if suffix == ".pdf":
            text = _parse_pdf(file_path)
        elif suffix == ".docx":
            text = _parse_docx(file_path)
        elif suffix == ".txt":
            text = _parse_txt(file_path)
        else:
            raise ValueError(f"No parser for format: {suffix}")

        logger.info(f"Parsed {file_path.name}: extracted {len(text)} characters")
        return text
    except Exception as e:
        logger.error(f"Parse failed for {file_path.name}: {type(e).__name__}: {e}", exc_info=True)
        raise


def _parse_pdf(file_path: Path) -> str:
    """Extract text from PDF file."""
    reader = PdfReader(file_path)
    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)
    return "\n\n".join(text_parts)


def _parse_docx(file_path: Path) -> str:
    """Extract text from DOCX file."""
    doc = DocxDocument(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _parse_txt(file_path: Path) -> str:
    """Extract text from TXT file."""
    return file_path.read_text(encoding="utf-8", errors="replace")
