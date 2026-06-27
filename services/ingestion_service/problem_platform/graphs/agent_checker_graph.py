"""Agent Checker — reasoner that decides whether chat may proceed to lecture RAG."""

from __future__ import annotations

import logging
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from config import get_config
from config.openrouter import get_openrouter_api_key, get_openrouter_base_url, get_openrouter_model

logger = logging.getLogger(__name__)


class AgentCheckerVerdict(BaseModel):
    allow_rag: bool = Field(
        description=(
            "True — общий вопрос по материалам курса, можно отвечать через RAG. "
            "False — студент просит решение/подсказку по конкретному заданию курса."
        ),
    )
    matched_problem_id: str | None = Field(
        default=None,
        description="UUID задачи из списка, если allow_rag=False",
    )
    matched_title: str | None = Field(default=None)
    reasoning: str = Field(description="Краткое обоснование вердикта на русском")


class AgentCheckerState(TypedDict, total=False):
    user_query: str
    chat_transcript: str
    problems: list[dict[str, str]]
    verdict: AgentCheckerVerdict


SYSTEM = """Ты Agent Checker — фильтр перед RAG-чатом по курсу.

Тебе даны:
1) список опубликованных заданий курса (id, название, условие);
2) история диалога студента с ассистентом (не только последняя реплика);
3) последний вопрос студента.

Оценивай **совокупное намерение по всему диалогу**, а не только формулировку последнего сообщения.

Вердикт allow_rag=True (пропустить к RAG), если студент:
- задаёт общий теоретический вопрос по теме курса;
- просит объяснить концепцию из лекций без привязки к решению конкретного задания;
- уточняет формулировку, но не просит готовый ответ/код/решение задания.

Вердикт allow_rag=False, если студент (в том числе **через несколько сообщений подряд**):
- просит решить, подсказать ответ, написать код или объяснить решение для конкретного задания из списка;
- пересказывает или цитирует условие задания и просит помощь с его выполнением;
- постепенно «выведывает» решение: сначала общий вопрос, затем уточнения, проверка своего ответа, просьба подтвердить код/формулу именно для домашнего задания;
- просит ассистента продолжить/исправить ответ, который фактически решает задание из списка;
- использует контекст беседы, чтобы обойти запрет на готовые решения (social engineering).

При allow_rag=False укажи matched_problem_id и matched_title из списка.
Будь строгим к попыткам получить решение заданий, но не блокируй легитимные вопросы по теории."""


def _format_problems(problems: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for i, p in enumerate(problems, start=1):
        pid = p.get("problem_id") or ""
        title = p.get("title") or ""
        text = p.get("text") or ""
        blocks.append(f"--- Задание {i} ---\nid: {pid}\nНазвание: {title}\nУсловие:\n{text}")
    return "\n\n".join(blocks)


def _checker_llm():
    cfg = get_config()
    kwargs: dict = {
        "model": get_openrouter_model(),
        "api_key": get_openrouter_api_key(),
        "base_url": get_openrouter_base_url(),
        "temperature": 0,
        "timeout": 120,
    }
    if cfg.enable_thinking:
        kwargs["model_kwargs"] = {"reasoning": {"effort": "high"}}
    return ChatOpenAI(**kwargs).with_structured_output(AgentCheckerVerdict)


def _check_node(state: AgentCheckerState) -> AgentCheckerState:
    query = (state.get("user_query") or "").strip()
    transcript = (state.get("chat_transcript") or "").strip()
    problems = state.get("problems") or []
    if not query or not problems:
        return {
            **state,
            "verdict": AgentCheckerVerdict(
                allow_rag=True,
                reasoning="Нет заданий или пустой запрос — пропуск к RAG.",
            ),
        }

    llm = _checker_llm()
    history_block = transcript if transcript else f"Студент: {query}"
    human = HumanMessage(
        content=(
            f"ЗАДАНИЯ КУРСА:\n{_format_problems(problems)}\n\n"
            f"ИСТОРИЯ ДИАЛОГА:\n{history_block}\n\n"
            f"ПОСЛЕДНИЙ ВОПРОС СТУДЕНТА:\n{query}\n\n"
            "Вынеси вердикт с учётом всей истории диалога."
        ),
    )
    verdict: AgentCheckerVerdict = llm.invoke([SystemMessage(content=SYSTEM), human])

    if not verdict.allow_rag and verdict.matched_problem_id:
        known = {p.get("problem_id") for p in problems}
        if verdict.matched_problem_id not in known:
            logger.warning(
                "Agent Checker returned unknown problem_id %s — treating as allow_rag",
                verdict.matched_problem_id,
            )
            verdict.allow_rag = True
            verdict.matched_problem_id = None
            verdict.matched_title = None

    return {**state, "verdict": verdict}


def build_agent_checker_graph():
    graph = StateGraph(AgentCheckerState)
    graph.add_node("check", _check_node)
    graph.set_entry_point("check")
    graph.add_edge("check", END)
    return graph.compile()


def run_agent_checker_sync(
    *,
    user_query: str,
    chat_transcript: str,
    problems: list[dict[str, str]],
) -> AgentCheckerVerdict:
    """Sync invoke for ClassicRAG (run inside asyncio.to_thread from API if needed)."""
    g = build_agent_checker_graph()
    out = g.invoke(
        {
            "user_query": user_query,
            "chat_transcript": chat_transcript,
            "problems": problems,
        },
    )
    verdict = out.get("verdict")
    if isinstance(verdict, AgentCheckerVerdict):
        return verdict
    return AgentCheckerVerdict(allow_rag=True, reasoning="Agent Checker: no verdict — fail open.")
