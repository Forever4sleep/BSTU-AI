"""Агент генерации черновиков: партии по 2–3 задачи, structured output (как draft_graph)."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from config.openrouter import get_openrouter_api_key, get_openrouter_base_url, get_openrouter_model
from langchain_openai import ChatOpenAI

from services.ingestion_service.problem_platform.graphs.draft_graph import (
    DraftBatchSchema,
    DraftItem,
    scroll_course_context,
)

logger = logging.getLogger(__name__)

ALLOWED_KINDS = ("coding", "mcq", "free_text")
KIND_ROTATION = ("coding", "mcq", "free_text")


class AgentBatchOutput(BaseModel):
    """Ответ модели на одну партию слотов (structured output — надёжнее tool calling на OpenRouter)."""

    thinking: str = Field(
        default="",
        description="Кратко: какие темы из лекции использованы и почему такие формулировки.",
    )
    problems: list[DraftItem] = Field(
        min_length=1,
        max_length=3,
        description="Черновики задач в том же порядке, что слоты партии.",
    )


def _expand_kinds_interleaved(kind_quota: dict[str, int]) -> list[str]:
    """Равномерно смешивает типы по round-robin, пока квоты не исчерпаны."""
    remaining = {k: int(kind_quota.get(k, 0) or 0) for k in KIND_ROTATION}
    result: list[str] = []
    while sum(remaining.values()) > 0:
        for k in KIND_ROTATION:
            if remaining[k] > 0:
                result.append(k)
                remaining[k] -= 1
    return result


def build_generation_slots(
    difficulty_quota: dict[int, int],
    kind_quota: dict[str, int] | None = None,
) -> list[dict[str, object]]:
    """Квоты по уровням 1..10 и (опционально) по типам coding / mcq / free_text."""
    difficulties: list[int] = []
    for level in range(1, 11):
        n = int(difficulty_quota.get(level, 0) or 0)
        difficulties.extend([level] * n)

    kind_total = 0
    if kind_quota:
        kind_total = sum(int(kind_quota.get(k, 0) or 0) for k in KIND_ROTATION)

    if kind_total > 0:
        kinds = _expand_kinds_interleaved(kind_quota or {})
        if len(difficulties) != len(kinds):
            n = min(len(difficulties), len(kinds))
            return [{"difficulty": difficulties[i], "kind": kinds[i]} for i in range(n)]
        return [{"difficulty": d, "kind": k} for d, k in zip(difficulties, kinds)]

    slots: list[dict[str, object]] = []
    for idx, level in enumerate(difficultities):
        slots.append({"difficulty": level, "kind": KIND_ROTATION[idx % len(KIND_ROTATION)]})
    return slots


def _validate_one(p: DraftItem) -> bool:
    return _validate_failure_reason(p) is None


def _validate_failure_reason(p: DraftItem) -> str | None:
    """None если ок, иначе короткая причина для журнала преподавателя."""
    allowed = set(ALLOWED_KINDS)
    k = (p.kind or "").strip().lower()
    if k not in allowed:
        return f"недопустимый kind «{p.kind}» (нужен coding / mcq / free_text)"
    p.kind = k
    if not (p.title or "").strip() or not (p.statement or "").strip():
        return "пустой title или statement"
    if p.kind == "coding":
        if not (p.starter_code or "").strip():
            return "coding: пустой starter_code"
        tests = p.coding_tests or []
        if not tests:
            return "coding: пустой список coding_tests (нужен ≥1 тест с stdin_data и expected_stdout)"
        if any(
            not (t.stdin_data or "").strip() or not (t.expected_stdout or "").strip()
            for t in tests
        ):
            return "coding: у теста пустые stdin_data или expected_stdout"
    elif p.kind == "mcq":
        opts = p.mcq_options or []
        if len(opts) < 2:
            return "mcq: нужно ≥2 варианта в mcq_options"
        if p.mcq_correct_index is None:
            return "mcq: не задан mcq_correct_index"
        if p.mcq_correct_index < 0 or p.mcq_correct_index >= len(opts):
            return "mcq: mcq_correct_index вне диапазона вариантов"
    elif p.kind == "free_text":
        if not (p.reference_answer or "").strip():
            return "free_text: пустой reference_answer"
    if p.difficulty is not None and (p.difficulty < 1 or p.difficulty > 10):
        return "сложность не в диапазоне 1–10"
    return None


class ProblemAgentState(TypedDict, total=False):
    course_id: str
    instructor_id: str
    document_ids: list[str]
    difficulty_quota: dict[int, int]
    kind_quota: dict[str, int]
    qdrant_collection_name: str | None
    context_text: str
    slots: list[dict[str, object]]
    remaining_slots: list[dict[str, object]]
    current_batch: list[dict[str, object]]
    last_batch_output: AgentBatchOutput | None
    accumulated_problems: list[DraftItem]
    drafts: DraftBatchSchema
    errors: list[str]
    agent_logs: list[str]


SYS_AGENT_BATCH = """Ты методист. По фрагментам лекции сгенерируй задачи строго для указанных слотов (тип и сложность заданы).
Верни JSON с полями thinking (краткий ход рассуждений) и problems (массив черновиков в порядке слотов).

Язык: все тексты только на русском — title, statement, starter_code, mcq_options, reference_answer, grading_rubric, thinking.

Формат каждого элемента problems (индекс = номер слота):
- kind: ровно одна строка: coding | mcq | free_text (как в слоте).
- title, statement — непустые строки на русском.
- coding: starter_code на Python с комментариями/строками на русском где уместно; coding_tests — массив объектов с полями stdin_data, expected_stdout, is_public (минимум один тест; stdin и stdout непустые).
- mcq: mcq_options (≥2 строки на русском), mcq_correct_index (целое 0..len-1).
- free_text: reference_answer — непустой эталон на русском.

Не добавляй факты вне фрагментов лекции."""


def _retrieve_node(state: ProblemAgentState) -> ProblemAgentState:
    doc_ids = state.get("document_ids") or []
    cn = state.get("qdrant_collection_name")
    context, scroll_errs = scroll_course_context(doc_ids, cn, max_chars=24_000)
    errs = list(state.get("errors") or []) + scroll_errs
    logs = list(state.get("agent_logs") or [])
    logs.append(f"[контекст] Загружены фрагменты лекции (~{len(context)} символов).")
    return {**state, "context_text": context, "errors": errs, "agent_logs": logs}


def _plan_node(state: ProblemAgentState) -> ProblemAgentState:
    raw = state.get("difficulty_quota") or {}
    dq = {int(k): int(v) for k, v in raw.items()}
    kq = state.get("kind_quota") or {}
    slots = build_generation_slots(dq, kq if kq else None)
    errs = list(state.get("errors") or [])
    logs = list(state.get("agent_logs") or [])
    if not slots:
        errs.append("Суммарная квота сложности равна 0 — нечего генерировать.")
    else:
        kind_counts = {k: sum(1 for s in slots if s.get("kind") == k) for k in KIND_ROTATION}
        kind_desc = ", ".join(f"{k}={kind_counts[k]}" for k in KIND_ROTATION if kind_counts[k])
        logs.append(f"[план] Построено слотов: {len(slots)} ({kind_desc or 'типы не заданы'}).")
    return {**state, "slots": slots, "errors": errs, "agent_logs": logs}


def _init_loop_node(state: ProblemAgentState) -> ProblemAgentState:
    slots = state.get("slots") or []
    logs = list(state.get("agent_logs") or [])
    logs.append("[цикл] Очередь слотов готова к покомандной генерации.")
    return {
        **state,
        "remaining_slots": [dict(s) for s in slots],
        "accumulated_problems": [],
        "agent_logs": logs,
    }


def _batch_prepare_node(state: ProblemAgentState) -> ProblemAgentState:
    rem = list(state.get("remaining_slots") or [])
    logs = list(state.get("agent_logs") or [])
    if not rem:
        return {**state, "current_batch": [], "agent_logs": logs}
    k = min(3, len(rem))
    batch = rem[:k]
    desc = ", ".join(f"{s['kind']}@{s['difficulty']}" for s in batch)
    logs.append(f"[партия] К модели: {len(batch)} задач ({desc}).")
    return {**state, "current_batch": batch, "agent_logs": logs}


def _route_after_prepare(state: ProblemAgentState) -> str:
    return "agent" if (state.get("current_batch") or []) else "validate"


def _agent_call_node(state: ProblemAgentState) -> ProblemAgentState:
    ctx = (state.get("context_text") or "").strip()
    batch = state.get("current_batch") or []
    logs = list(state.get("agent_logs") or [])
    errs = list(state.get("errors") or [])

    if not ctx:
        logs.append("[модель] Нет контекста — пропуск партии.")
        return {**state, "last_batch_output": None, "agent_logs": logs}
    if not batch:
        return {**state, "last_batch_output": None, "agent_logs": logs}

    llm = ChatOpenAI(
        model=get_openrouter_model(),
        api_key=get_openrouter_api_key(),
        base_url=get_openrouter_base_url(),
        temperature=0.35,
        timeout=180,
    ).with_structured_output(AgentBatchOutput)

    slot_lines = [
        f"- Слот {i + 1}: тип {s['kind']}, сложность {int(s['difficulty'])}/10"
        for i, s in enumerate(batch)
    ]
    human = (
        f"Сгенерируй ровно {len(batch)} задач по слотам ниже. "
        f"В problems должно быть ровно {len(batch)} элементов (порядок = слоты). "
        f"Все условия, варианты и эталоны — на русском языке.\n\n"
        "Слоты:\n"
        + "\n".join(slot_lines)
        + "\n\nФрагменты лекции:\n\n"
        + ctx
    )

    try:
        batch_out = llm.invoke([SystemMessage(content=SYS_AGENT_BATCH), HumanMessage(content=human)])
        if not isinstance(batch_out, AgentBatchOutput):
            logs.append("[модель] Некорректный тип structured output.")
            return {**state, "last_batch_output": None, "agent_logs": logs, "errors": errs}
        logs.append(f"[модель] Structured output: {len(batch_out.problems)} задач.")
        return {**state, "last_batch_output": batch_out, "agent_logs": logs}
    except Exception as e:
        logger.exception("problem_agent: invoke failed")
        errs.append(f"llm-invoke: {type(e).__name__}: {e}")
        logs.append(f"[модель] Ошибка вызова: {type(e).__name__}: {e}")
        return {**state, "last_batch_output": None, "agent_logs": logs, "errors": errs}


def _output_drafts_node(state: ProblemAgentState) -> ProblemAgentState:
    batch = state.get("current_batch") or []
    remaining = list(state.get("remaining_slots") or [])
    accumulated = list(state.get("accumulated_problems") or [])
    logs = list(state.get("agent_logs") or [])
    errs = list(state.get("errors") or [])
    batch_out = state.get("last_batch_output")

    new_remaining = remaining[len(batch) :] if batch else remaining

    if not batch:
        return {**state, "remaining_slots": new_remaining, "agent_logs": logs}

    if batch_out is None:
        logs.append("[вывод] Нет ответа модели — партия пропущена.")
        return {**state, "remaining_slots": new_remaining, "agent_logs": logs, "errors": errs}

    thinking = (batch_out.thinking or "").strip()
    if thinking:
        logs.append(f"[агент] {thinking}")

    problems_raw = list(batch_out.problems or [])

    accepted = 0
    for i, slot in enumerate(batch):
        k_slot = str(slot["kind"]).strip().lower()
        if i >= len(problems_raw):
            msg = f"[вывод] Слот {i + 1} ({k_slot}): нет элемента problems[{i}]"
            logs.append(msg)
            errs.append(f"batch-item-missing-{i + 1}")
            continue
        item = problems_raw[i]
        if not isinstance(item, DraftItem):
            try:
                item = DraftItem.model_validate(item)
            except Exception as e:
                logs.append(f"[вывод] Слот {i + 1}: ошибка разбора — {type(e).__name__}: {e}")
                errs.append(f"parse-slot-{i + 1}: {type(e).__name__}: {e}")
                continue
        try:
            item.kind = k_slot
            item.difficulty = int(slot["difficulty"])
            reason = _validate_failure_reason(item)
            if reason is None:
                accumulated.append(item)
                accepted += 1
            else:
                logs.append(f"[вывод] Слот {i + 1} ({k_slot}): не принято — {reason}")
                errs.append(f"validation-slot-{i + 1}: {reason}")
        except Exception as e:
            logs.append(f"[вывод] Слот {i + 1}: ошибка — {type(e).__name__}: {e}")
            errs.append(f"parse-slot-{i + 1}: {type(e).__name__}: {e}")

    logs.append(f"[вывод] Принято черновиков в партии: {accepted} из {len(batch)}.")

    return {
        **state,
        "remaining_slots": new_remaining,
        "accumulated_problems": accumulated,
        "last_batch_output": None,
        "agent_logs": logs,
        "errors": errs,
    }


def _route_after_output(state: ProblemAgentState) -> str:
    rem = state.get("remaining_slots") or []
    return "more" if rem else "done"


def _validate_node(state: ProblemAgentState) -> ProblemAgentState:
    raw_list = list(state.get("accumulated_problems") or [])
    keep = [p for p in raw_list if _validate_one(p)]
    logs = list(state.get("agent_logs") or [])
    logs.append(f"[итог] Валидных черновиков: {len(keep)} из {len(raw_list)}.")
    return {**state, "drafts": DraftBatchSchema(problems=keep), "agent_logs": logs}


def build_problem_agent_graph():
    graph = StateGraph(ProblemAgentState)
    graph.add_node("retrieve", _retrieve_node)
    graph.add_node("plan", _plan_node)
    graph.add_node("init_loop", _init_loop_node)
    graph.add_node("batch_prepare", _batch_prepare_node)
    graph.add_node("agent_call", _agent_call_node)
    graph.add_node("output_drafts", _output_drafts_node)
    graph.add_node("validate", _validate_node)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "plan")
    graph.add_edge("plan", "init_loop")
    graph.add_edge("init_loop", "batch_prepare")

    graph.add_conditional_edges(
        "batch_prepare",
        _route_after_prepare,
        {"agent": "agent_call", "validate": "validate"},
    )
    graph.add_edge("agent_call", "output_drafts")
    graph.add_conditional_edges(
        "output_drafts",
        _route_after_output,
        {"more": "batch_prepare", "done": "validate"},
    )
    graph.add_edge("validate", END)
    return graph.compile()


def run_problem_agent_sync(
    initial: ProblemAgentState,
    *,
    on_progress: Any | None = None,
) -> ProblemAgentState:
    """
    Запуск графа. Если передан on_progress(dict), вызывается после каждого шага (stream values):
    dict может содержать keys: agent_logs, label (последняя строка лога).
    """
    g = build_problem_agent_graph()
    final: ProblemAgentState | None = None
    init = dict(initial)
    if "agent_logs" not in init:
        init["agent_logs"] = []
    try:
        for state in g.stream(init, stream_mode="values"):
            final = dict(state)  # type: ignore[arg-type]
            if on_progress and final.get("agent_logs") is not None:
                logs = final.get("agent_logs") or []
                on_progress(
                    {
                        "logs": list(logs),
                        "label": logs[-1] if logs else "",
                    },
                )
    except Exception:
        logger.exception("problem_agent stream failed")
        raise
    return final or init

