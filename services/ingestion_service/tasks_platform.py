"""Celery-задачи платформы (генерация черновиков)."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session, selectinload

from services.ingestion_service.celery_app import celery_app
from services.ingestion_service.db.problem_models import (
    Course,
    DocumentCatalog,
    DraftStatus,
    Problem,
    ProblemDraft,
    ProblemKind,
    Submission,
)
from services.ingestion_service.db.sync_engine import create_sync_engine_from_config
from services.ingestion_service.problem_platform.graphs.draft_graph import (
    DraftGenState,
    run_draft_graph_sync,
)
from services.ingestion_service.problem_platform.graphs.problem_generation_graph import (
    ProblemAgentState,
    run_problem_agent_sync,
)
from services.ingestion_service.problem_platform.graphs.reference_graph import (
    run_reference_judge_sync,
)
from services.ingestion_service.problem_platform.qdrant_naming import (
    course_collection_from_slug,
)

logger = logging.getLogger(__name__)


def _course_document_ids(session: Session, course_id: uuid.UUID) -> list[str]:
    c = session.get(Course, course_id, options=[selectinload(Course.documents)])
    if not c:
        return []
    return [str(d.id) for d in (c.documents or [])]


@celery_app.task(bind=True, name="platform.generate_course_drafts")
def generate_course_drafts(
    self,
    course_id: str,
    instructor_id: str,
    topic_queries: list[str],
    max_items: int,
) -> dict:
    cid = uuid.UUID(course_id)
    iid = uuid.UUID(instructor_id)
    _, SessionLocal = create_sync_engine_from_config()
    with SessionLocal() as session:
        doc_ids = _course_document_ids(session, cid)
        course_row = session.get(Course, cid)
        qdrant_cn = ""
        if course_row:
            qdrant_cn = (course_row.qdrant_collection_name or "").strip() or course_collection_from_slug(
                course_row.slug,
            )
        state: DraftGenState = {
            "course_id": course_id,
            "instructor_id": instructor_id,
            "document_ids": doc_ids,
            "topic_queries": topic_queries,
            "max_items": max_items,
            "qdrant_collection_name": qdrant_cn or None,
        }
        logger.info(
            "platform.generate_course_drafts: course=%s topics=%s docs=%s",
            course_id,
            topic_queries,
            len(doc_ids),
        )
        out = run_draft_graph_sync(state)
        drafts_schema = out.get("drafts")
        problems_list = []
        if drafts_schema is not None:
            if hasattr(drafts_schema, "problems"):
                problems_list = list(drafts_schema.problems)
            elif isinstance(drafts_schema, dict):
                raw = drafts_schema.get("problems") or []
                from services.ingestion_service.problem_platform.graphs.draft_graph import (
                    DraftItem,
                )

                problems_list = [DraftItem.model_validate(x) for x in raw]
        inserted = []
        for item in problems_list:
            pk = ProblemDraft(
                course_id=cid,
                instructor_id=iid,
                status=DraftStatus.pending_review.value,
                kind=item.kind,
                title=(item.title or "Черновик")[:511],
                payload=item.model_dump(mode="json"),
                provenance={"topic_queries": topic_queries, "source": "draft_graph"},
                celery_job_id=self.request.id,
            )
            session.add(pk)
            session.flush()
            inserted.append({"draft_id": str(pk.id)})

        session.commit()
        return {
            "created": len(inserted),
            "drafts": inserted,
            "warnings": list(out.get("errors") or []),
            "documents_used": doc_ids,
        }


@celery_app.task(bind=True, name="platform.generate_agent_drafts")
def generate_agent_drafts(
    self,
    course_id: str,
    instructor_id: str,
    document_ids: list[str],
    difficulty_quota: dict[str, int],
    kind_quota: dict[str, int] | None = None,
) -> dict:
    """
    Генерация черновиков по выбранным лекциям, квотам сложности 1–10 и типам задач.
    ``difficulty_quota``: ключи «1»..«10», значения — число задач на уровне.
    ``kind_quota``: ключи coding / mcq / free_text — число задач каждого типа.
    """
    cid = uuid.UUID(course_id)
    iid = uuid.UUID(instructor_id)
    _, SessionLocal = create_sync_engine_from_config()

    dq = {int(k): int(v) for k, v in difficulty_quota.items()}
    kq = {k: int(v) for k, v in (kind_quota or {}).items()}
    total_slots = sum(dq.values())
    kind_total = sum(kq.values())
    if total_slots < 1:
        return {"created": 0, "drafts": [], "warnings": ["Пустая квота сложности."], "documents_used": []}
    if kind_total > 0 and kind_total != total_slots:
        return {
            "created": 0,
            "drafts": [],
            "warnings": [f"Сумма по типам ({kind_total}) не совпадает с суммой по сложности ({total_slots})."],
            "documents_used": [],
        }

    with SessionLocal() as session:
        allowed = set(_course_document_ids(session, cid))
        req = set(document_ids)
        if not req:
            return {"created": 0, "drafts": [], "warnings": ["Не выбраны документы (лекции)."], "documents_used": []}
        if not req.issubset(allowed):
            bad = req - allowed
            return {
                "created": 0,
                "drafts": [],
                "warnings": [f"Документы не из этого курса: {sorted(bad)[:12]}"],
                "documents_used": [],
            }

        course_row = session.get(Course, cid)
        qdrant_cn = ""
        if course_row:
            qdrant_cn = (course_row.qdrant_collection_name or "").strip() or course_collection_from_slug(
                course_row.slug,
            )

        state: ProblemAgentState = {
            "course_id": course_id,
            "instructor_id": instructor_id,
            "document_ids": list(document_ids),
            "difficulty_quota": dq,
            "kind_quota": kq,
            "qdrant_collection_name": qdrant_cn or None,
        }
        logger.info(
            "platform.generate_agent_drafts: course=%s docs=%s quota_sum=%s",
            course_id,
            len(document_ids),
            total_slots,
        )

        def _professor_progress_from_log(raw: str) -> tuple[str, str]:
            """Внутренние логи агента → фаза и подпись для UI преподавателя."""
            label = (raw or "").strip()
            if not label or label.startswith("Старт"):
                return "queue", "Подготовка генератора…"
            if label.startswith("[контекст]") or label.startswith("[цикл]"):
                return "analyze", "Изучаем выбранные лекции…"
            if label.startswith("[план]"):
                return "analyze", "Распределяем задачи по сложности…"
            if label.startswith("[партия]"):
                return "generate", "ИИ составляет условия и ответы…"
            if label.startswith("[модель]"):
                return "generate", "Обрабатываем очередную партию…"
            if label.startswith("[агент]"):
                return "generate", "Уточняем формулировки…"
            if label.startswith("[вывод]"):
                return "generate", "Проверяем черновики…"
            if label.startswith("[итог]"):
                return "finish", "Завершаем генерацию…"
            return "generate", "Генерируем задания…"

        def _emit_agent_progress(payload: dict) -> None:
            logs = payload.get("logs") or []
            raw_label = (payload.get("label") or "").strip()
            if not raw_label and logs:
                raw_label = str(logs[-1]).strip()
            phase, label = _professor_progress_from_log(raw_label)
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": phase,
                    "label": label,
                },
            )

        _emit_agent_progress({"label": "Старт"})
        out = run_problem_agent_sync(state, on_progress=_emit_agent_progress)

        drafts_schema = out.get("drafts")
        problems_list = []
        if drafts_schema is not None:
            if hasattr(drafts_schema, "problems"):
                problems_list = list(drafts_schema.problems)
            elif isinstance(drafts_schema, dict):
                raw = drafts_schema.get("problems") or []
                from services.ingestion_service.problem_platform.graphs.draft_graph import DraftItem

                problems_list = [DraftItem.model_validate(x) for x in raw]

        inserted = []
        for item in problems_list:
            payload = item.model_dump(mode="json")
            pk = ProblemDraft(
                course_id=cid,
                instructor_id=iid,
                status=DraftStatus.pending_review.value,
                kind=item.kind,
                title=(item.title or "Черновик")[:511],
                payload=payload,
                provenance={
                    "source": "problem_agent",
                    "document_ids": list(document_ids),
                    "difficulty_quota": {str(k): v for k, v in dq.items()},
                    "kind_quota": kq,
                    "celery_task_id": self.request.id,
                },
                celery_job_id=self.request.id,
            )
            session.add(pk)
            session.flush()
            inserted.append({"draft_id": str(pk.id)})

        session.commit()
        return {
            "created": len(inserted),
            "drafts": inserted,
            "warnings": list(out.get("errors") or []),
            "documents_used": list(document_ids),
        }


@celery_app.task(bind=True, name="platform.grade_free_text")
def grade_free_text_submission(
    self,
    problem_id: str,
    participant_id: str,
    student_text: str,
) -> dict:
    """Асинхронная оценка свободного ответа (LLM-судья) с логами в PROGRESS."""
    logs: list[str] = []

    def emit(msg: str) -> None:
        logs.append(msg)
        self.update_state(
            state="PROGRESS",
            meta={
                "phase": "grade",
                "label": msg[:400],
                "logs": logs[-100:],
            },
        )

    emit("[оценка] Поставлено в очередь…")
    pid = uuid.UUID(problem_id)
    _, SessionLocal = create_sync_engine_from_config()

    with SessionLocal() as session:
        p = session.get(Problem, pid)
        if not p or not p.published:
            emit("[оценка] Ошибка: задача недоступна.")
            return {"error": "problem_not_found", "agent_logs": logs}

        if not (p.reference_answer or "").strip():
            emit("[оценка] Ошибка: у задачи нет эталона.")
            return {"error": "missing_reference", "agent_logs": logs}

        emit("[оценка] Вызов модели-судьи (это может занять до ~2 мин.)…")
        jstate = run_reference_judge_sync(
            {
                "problem_statement": p.statement,
                "reference_answer": p.reference_answer,
                "rubric": p.grading_rubric or "",
                "student_answer": student_text,
                "max_score": float(p.max_score),
            },
        )
        jd = jstate.get("judgement")
        if hasattr(jd, "model_dump"):
            verdict_j = jd.model_dump()
        elif isinstance(jd, dict):
            verdict_j = jd
        else:
            verdict_j = {"score": 0.0, "feedback_ru": str(jd)}

        score = float(verdict_j.get("score", 0))
        verdict_out = {"verdict": "GRADED", **verdict_j}

        sub = Submission(
            problem_id=p.id,
            participant_id=participant_id[:128],
            free_text_answer=student_text,
            verdict_json=verdict_out | {"agent_logs": logs},
            score=score,
        )
        session.add(sub)
        session.commit()
        emit(f"[оценка] Готово: балл {score} / {float(p.max_score)}.")

        return verdict_out | {
            "stored_submission_id": str(sub.id),
            "agent_logs": logs,
        }
