"""Граф эталонного судьи свободного ответа (один узел LLM + структура оценки)."""

from __future__ import annotations

import logging
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from pydantic import BaseModel, Field

from config.openrouter import get_openrouter_api_key, get_openrouter_base_url, get_openrouter_model
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class JudgeLLM(BaseModel):
    score: float = Field(description="баллы 0 до max_score")
    feedback_ru: str = Field(description="структурированный разбор по рубрике")


class RefJudgeState(TypedDict, total=False):
    problem_statement: str
    reference_answer: str
    rubric: str
    student_answer: str
    max_score: float
    judgement: JudgeLLM


SYSTEM = (
    "Ты строгий проверяющий. Ставишь балл только если ответ студента содержимо сопоставим с эталоном преподавателя. "
    "Не добавляй знание вне эталона. Весь текст feedback_ru — только на русском языке."
)


def _grade_node(state: RefJudgeState) -> RefJudgeState:
    max_score = float(state.get("max_score") or 10)
    stmt = state.get("problem_statement") or ""
    ref = state.get("reference_answer") or ""
    rub = state.get("rubric") or ""
    answ = state.get("student_answer") or ""

    llm = ChatOpenAI(
        model=get_openrouter_model(),
        api_key=get_openrouter_api_key(),
        base_url=get_openrouter_base_url(),
        temperature=0.1,
        timeout=120,
    ).with_structured_output(JudgeLLM)

    human = HumanMessage(
        content=(
            f"Максимум баллов: {max_score}\n\n"
            f"УСЛОВИЕ ЗАДАЧИ:\n{stmt}\n\n"
            f"ЭТАЛОН (внутренний, не сообщать студенту):\n{ref}\n\n"
            f"РУБРИКА / ИНСТРУКЦИИ ДЛЯ ОЦЕНКИ:\n{rub}\n\n"
            f"ОТВЕТ СТУДЕНТА:\n{answ}\n\n"
            f"Выставь балл от 0 до {max_score} и фидбек."
        )
    )
    verdict: JudgeLLM = llm.invoke([SystemMessage(content=SYSTEM), human])
    if verdict.score < 0:
        verdict.score = 0
    if verdict.score > max_score:
        verdict.score = max_score
    return {**state, "judgement": verdict}


def build_reference_judge_graph():
    graph = StateGraph(RefJudgeState)
    graph.add_node("grade", _grade_node)
    graph.set_entry_point("grade")
    graph.add_edge("grade", END)
    return graph.compile()


def run_reference_judge_sync(payload: RefJudgeState) -> RefJudgeState:
    """Синхронный вызов из FastAPI через asyncio.to_thread при необходимости."""
    g = build_reference_judge_graph()
    return dict(g.invoke(payload))
