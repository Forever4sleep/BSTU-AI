"""
Document Parsers

Все форматы через Docling (VLM для PDF, нативные бэкенды для остальных).
TXT: read_text (Docling не поддерживает plain text).
"""

import logging
from pathlib import Path

from config import get_config

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    VlmConvertOptions,
    VlmPipelineOptions,
)
from docling.datamodel.vlm_engine_options import (
    ApiVlmEngineOptions,
    VlmEngineType,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline

logger = logging.getLogger(__name__)

# Docling: PDF, DOCX, PPTX, XLSX, MD, HTML, CSV, изображения
# TXT: вне Docling
SUPPORTED_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".doc", ".pptx", ".xlsx",
    ".md", ".html", ".htm", ".csv",
    ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp",
    ".txt",
})

# Расширения, которые Docling обрабатывает (не TXT)
_DOCLING_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".doc", ".pptx", ".xlsx",
    ".md", ".html", ".htm", ".csv",
    ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp",
})


def _create_converter():
    """Создать DocumentConverter: VLM для PDF, дефолты для остальных форматов."""

    cfg = get_config()
    api_key = cfg.openrouter_api_key or cfg.openai_api_key
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY или OPENAI_API_KEY не задан для VLM")

    # OpenRouter: https://github.com/docling-project/docling/issues/2214
    # granite_docling expects DocTags → Qwen returns Markdown → empty. Use "qwen" preset (Markdown).
    # https://github.com/docling-project/docling/issues/3033
    base_options = VlmConvertOptions.from_preset(
        "qwen",
        engine_options=ApiVlmEngineOptions(
            runtime_type=VlmEngineType.API,
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            params={
                "model": cfg.vlm_model,
                "max_tokens": 4096,
            },
            timeout=cfg.vlm_timeout,
        ),
    )
    updated_spec = base_options.model_spec.model_copy(
        update={"default_repo_id": cfg.vlm_model}
    )
    vlm_options = base_options.model_copy(update={"model_spec": updated_spec})

    pipeline_options = VlmPipelineOptions(
        vlm_options=vlm_options,
        enable_remote_services=True,
    )

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                pipeline_cls=VlmPipeline,
            )
        }
    )


_converter = None


def _get_converter():
    global _converter
    if _converter is None:
        _converter = _create_converter()
    return _converter


def parse_document(file_path: Path) -> str:
    """
    Parse a document and extract text.

    PDF: Docling VLM (qwen-2.5-vl via OpenRouter).
    DOCX, PPTX, XLSX, MD, HTML, CSV, изображения: Docling нативные бэкенды.
    TXT: read_text.
    """
    suffix = file_path.suffix.lower()
    if suffix == ".doc":
        suffix = ".docx"

    logger.info(f"Parsing document: {file_path.name}, format={suffix}")

    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: {suffix}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    try:
        if suffix == ".txt":
            text = _parse_txt(file_path)
        elif suffix in _DOCLING_EXTENSIONS:
            text = _parse_with_docling(file_path)
        else:
            raise ValueError(f"No parser for format: {suffix}")

        logger.info(f"Parsed {file_path.name}: extracted {len(text)} characters")
        return text
    except Exception as e:
        logger.error(
            f"Parse failed for {file_path.name}: {type(e).__name__}: {e}",
            exc_info=True,
        )
        raise


def _parse_with_docling(file_path: Path) -> str:
    """Извлечь текст через Docling (все форматы кроме TXT)."""
    converter = _get_converter()
    path_str = str(file_path.resolve())
    result = converter.convert(path_str)
    return result.document.export_to_markdown()


def _parse_txt(file_path: Path) -> str:
    """Plain text (Docling не поддерживает)."""
    return file_path.read_text(encoding="utf-8", errors="replace")
