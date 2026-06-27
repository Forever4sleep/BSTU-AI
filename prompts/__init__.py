"""
YAML-backed prompt templates (loaders + dataclasses).

Add new `.yaml` files here and expose a typed loader below.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent


@dataclass(frozen=True)
class ClassifiedRAGPromptTemplate:
    """Loaded from classified_rag.yaml — used by ContextPromptBuilder."""

    context_marker: str
    instructions: str
    no_hits_note: str
    low_relevance_response: str
    context_header: str
    context_footer: str

    def build_system_content(self, context_block: str, *, had_hits: bool) -> str:
        if had_hits and context_block.strip():
            return (
                f"{self.context_marker}\n"
                f"{self.instructions}\n\n"
                f"{self.context_header}\n{context_block}\n"
                f"{self.context_footer}"
            )
        return f"{self.context_marker}\n{self.instructions}\n\n{self.no_hits_note}"


def load_classified_rag_prompts(path: Path | None = None) -> ClassifiedRAGPromptTemplate:
    """Load `classified_rag.yaml` (or the given path)."""
    prompt_path = path or (prompts_dir() / "classified_rag.yaml")
    raw = yaml.safe_load(prompt_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid YAML root in {prompt_path}")

    def req(key: str) -> str:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise KeyError(f"Missing or empty string key {key!r} in {prompt_path}")
        return value.strip()

    return ClassifiedRAGPromptTemplate(
        context_marker=req("context_marker"),
        instructions=req("instructions"),
        no_hits_note=req("no_hits_note"),
        low_relevance_response=req("low_relevance_response"),
        context_header=req("context_header"),
        context_footer=req("context_footer"),
    )


__all__ = [
    "ClassifiedRAGPromptTemplate",
    "load_classified_rag_prompts",
    "prompts_dir",
]
