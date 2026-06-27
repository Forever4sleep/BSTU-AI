"""Граф генерации черновиков задач из фрагментов Qdrant (RAG — отбор текста перед LLM)."""

from __future__ import annotations

import logging
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from pydantic import BaseModel, Field

from config import get_config
from config.openrouter import get_openrouter_api_key, get_openrouter_base_url, get_openrouter_model
from langchain_openai import ChatOpenAI

from services.ingestion_service.qdrant_client import create_qdrant_client
from qdrant_client.models import FieldCondition, Filter, MatchAny

logger = logging.getLogger(__name__)


class CodingTestSpec(BaseModel):
    stdin_data: str = ""
    expected_stdout: str = ""
    is_public: bool = True


class DraftItem(BaseModel):
    kind: str = Field(description="coding | mcq | free_text")
    title: str = ""
    statement: str = ""
    starter_code: str | None = None
    mcq_options: list[str] | None = None
    mcq_correct_index: int | None = None
    reference_answer: str | None = None
    grading_rubric: str | None = None
    coding_tests: list[CodingTestSpec] | None = None
    difficulty: int | None = Field(default=None, ge=1, le=10, description="Сложность 1–10 (агент генерации)")


class DraftBatchSchema(BaseModel):
    problems: list[DraftItem] = Field(default_factory=list)


class DraftGenState(TypedDict, total=False):
    course_id: str
    instructor_id: str
    document_ids: list[str]
    topic_queries: list[str]
    max_items: int
    context_text: str
    drafts: DraftBatchSchema
    errors: list[str]
    qdrant_collection_name: str | None


def scroll_course_context(
    document_ids: list[str],
    qdrant_collection_name: str | None,
    *,
    max_chars: int = 24_000,
) -> tuple[str, list[str]]:
    """
    Собирает текст фрагментов из Qdrant по catalog_document_id (без LangGraph).

    Returns:
        (context_text, errors) — при пустом контексте errors nonempty.
    """
    cfg = get_config()
    cn = (qdrant_collection_name or "").strip() or cfg.qdrant_collection_name
    client = create_qdrant_client()
    chunks: list[str] = []

    flt = None
    if document_ids:
        flt = Filter(
            must=[
                FieldCondition(
                    key="metadata.catalog_document_id",
                    match=MatchAny(any=document_ids),
                ),
            ],
        )

    offset = None
    while True:
        records, offset = client.scroll(
            collection_name=cn,
            scroll_filter=flt,
            offset=offset,
            with_payload=True,
            with_vectors=False,
            limit=64,
        )
        for record in records or []:
            pl = getattr(record, "payload", None) or {}
            text = pl.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
                if sum(len(x) for x in chunks) > max_chars:
                    break
            if sum(len(x) for x in chunks) > max_chars:
                break
        if offset is None or sum(len(x) for x in chunks) > max_chars:
            break

    if not chunks:
        return "", [f"Нет фрагментов в Qdrant для документов {document_ids}; коллекция «{cn}»."]

    glued: list[str] = []
    seen: set[str] = set()
    for c in chunks:
        key = c[:80]
        if key in seen:
            continue
        seen.add(key)
        glued.append(c)
        if sum(len(g) + 50 for g in glued) >= max_chars:
            break

    context = "\n\n--- FRAGMENT ---\n\n".join(glued)
    logger.info(
        "scroll_course_context: fragments=%s chars=%s docs=%s",
        len(glued),
        len(context),
        len(document_ids),
    )
    return context, []


SYSTEM_PROMPT_RU = """Ты методист. Тебе переданы только фрагменты методичности.
Сгенерируй учебные задачи строго в рамках этих фрагментов, без добавления внешних фактов.

Язык: все формулировки только на русском — названия, условия, варианты ответов, эталоны, пояснения.

Для каждой задачи kind:
- coding: starter_code — шаблон на Python (def solve…); тесты с короткими строками
- mcq: 4 варианта ответа на русском, один правильный индекс
- free_text: reference_answer — эталон для преподавателя на русском

Указывай для coding публичные и скрытые тест-кейсы (короткие строковые примеры)."""


def _retrieve_node(state: DraftGenState) -> DraftGenState:
    doc_ids = state.get("document_ids") or []
    topics = ", ".join(state.get("topic_queries") or []) or "(общее)"
    cn = state.get("qdrant_collection_name")
    context, errs = scroll_course_context(doc_ids, cn, max_chars=24_000)
    if errs:
        return {
            **state,
            "context_text": "",
            "errors": (state.get("errors") or []) + errs + [f"topics hint: {topics}"],
        }
    return {**state, "context_text": context}


def _generate_node(state: DraftGenState) -> DraftGenState:
    errs = list(state.get("errors") or [])
    ctx = (state.get("context_text") or "").strip()
    if not ctx:
        errs.append("empty-context")
        return {**state, "errors": errs, "drafts": DraftBatchSchema(problems=[])}

    max_items = int(state.get("max_items") or 3)
    topics = state.get("topic_queries") or []
    user = (
        f"Запросы тем: {topics}\n"
        f"Сгенерируй до {max_items} задач (разные типы по возможности). "
        f"Все условия и решения — на русском языке.\n"
        "Фрагменты источника:\n\n"
        f"{ctx}"
    )

    llm = ChatOpenAI(
        model=get_openrouter_model(),
        api_key=get_openrouter_api_key(),
        base_url=get_openrouter_base_url(),
        temperature=0.35,
        timeout=120,
    ).with_structured_output(DraftBatchSchema)

    batch: DraftBatchSchema = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT_RU),
            HumanMessage(content=user),
        ]
    )

    if batch.problems and len(batch.problems) > max_items:
        draft = DraftBatchSchema(problems=batch.problems[:max_items])
    else:
        draft = batch

    return {**state, "drafts": draft, "errors": errs}


def _validate_node(state: DraftGenState) -> DraftGenState:
    errs = list(state.get("errors") or [])
    drafts = state.get("drafts") or DraftBatchSchema(problems=[])
    keep: list[DraftItem] = []
    allowed = {"coding", "mcq", "free_text"}
    for p in drafts.problems:
        k = (p.kind or "").strip().lower()
        if k not in allowed:
            continue
        p.kind = k
        if not (p.title or "").strip() or not (p.statement or "").strip():
            continue
        if p.kind == "coding" and not (p.starter_code or "").strip():
            continue
        if p.kind == "coding" and not (p.coding_tests or []):
            continue
        if p.kind == "mcq" and (not (p.mcq_options or []) or len(p.mcq_options or []) < 2):
            continue
        if p.kind == "mcq" and p.mcq_correct_index is None:
            continue
        if p.kind == "free_text" and not (p.reference_answer or "").strip():
            continue
        keep.append(p)

    return {**state, "drafts": DraftBatchSchema(problems=keep), "errors": errs}


def build_draft_generation_graph():
    graph = StateGraph(DraftGenState)
    graph.add_node("retrieve", _retrieve_node)
    graph.add_node("generate", _generate_node)
    graph.add_node("validate", _validate_node)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


def run_draft_graph_sync(initial: DraftGenState) -> DraftGenState:
    g = build_draft_generation_graph()
    return dict(g.invoke(initial))
