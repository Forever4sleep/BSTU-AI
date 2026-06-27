"""
OpenAI-Compatible API Routes (v1)

Proxies requests to OpenRouter for OpenWebUI and other OpenAI-compatible clients.
Optional RAG: augments chat messages with Qdrant retrieval (see rag/ package).
"""

import asyncio
import base64
import copy
import functools
import json
import logging
import re
import time
import uuid
from typing import Literal

import httpx
import langsmith as ls
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langsmith import traceable

from config import get_config
from rag.factory import RAGFactory
from config.openrouter import (
    get_openrouter_api_key,
    get_openrouter_model,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestion_service.db.problem_models import Course as Pcourse
from services.ingestion_service.db.problem_models import CourseGroupAccess, PlatformStudent
from services.ingestion_service.db.repository import ConversationRepository, derive_thread_id
from services.ingestion_service.problem_platform.qdrant_naming import course_collection_from_slug
from services.ingestion_service.problem_platform.platform_auth import (
    decode_instructor_id_from_jwt,
    decode_student_id_from_jwt,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["OpenAI-совместимый API"])

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_TIMEOUT_SECONDS = 120.0

# Как для курсов в platform_routes (латиница, slug в БД в нижнем регистре)
_BSTU_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{2,126}$")


# ── helpers ────────────────────────────────────────────────────────


def _bstu_slug_param_ok(slug: str) -> bool:
    s = slug.strip().lower()
    return bool(s and _BSTU_SLUG_RE.match(s))


def _extract_non_stream_content(data: dict) -> str:
    """Pull assistant text from a standard (non-streaming) OpenAI response."""
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""


def _extract_streaming_content(chunks: list[str]) -> str:
    """Reassemble assistant text from collected SSE data chunks."""
    parts: list[str] = []
    for raw in chunks:
        for line in raw.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line.removeprefix("data:").strip()
            if payload == "[DONE]":
                continue
            try:
                obj = json.loads(payload)
                delta = obj["choices"][0]["delta"]
                if "content" in delta:
                    parts.append(delta["content"])
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue
    return "".join(parts)


def _build_headers(auth: str, request: Request | None = None) -> dict[str, str]:
    """Build upstream request headers, adding referer when request is provided."""
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
    }
    if request is not None:
        headers["HTTP-Referer"] = str(request.base_url)
    return headers


_SKIP_RAG_MARKERS = ("follow-up", "follow_ups", "chat_history")


def _is_meta_request(messages: list[dict]) -> bool:
    """Detect Open WebUI internal requests (follow-up generation, etc.)."""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and all(m in content.lower() for m in _SKIP_RAG_MARKERS):
            return True
    return False


def _apply_rag_to_chat_body(
    body: dict,
    request: Request,
    *,
    collection_override: str | None = None,
    course_slug: str | None = None,
    anti_cheat_mode: str = "off",
) -> dict:
    """Deep-copy body and inject retrieved context into messages (sync; run in thread)."""
    cfg = get_config()
    if not cfg.rag_enabled:
        return body

    rag = None
    if collection_override:
        client = getattr(request.app.state, "qdrant_client", None)
        if client is None:
            return body
        rag = RAGFactory.classic_for_collection(
            client,
            collection_override,
            course_slug=course_slug,
            anti_cheat_mode=anti_cheat_mode,
        )
    else:
        rag = getattr(request.app.state, "rag", None)
    if rag is None:
        return body

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return body

    if _is_meta_request(messages):
        logger.debug("Skipping RAG for meta-request (follow-up generation)")
        return body

    out = copy.deepcopy(body)
    msgs = out.get("messages")
    if not isinstance(msgs, list):
        return out

    rag.augment(msgs)
    return out


async def _student_may_use_course_chat_rag(session: AsyncSession, student: PlatformStudent, course: Pcourse) -> bool:
    """Студент: курс с чатом, публичный или групповой доступ с chat_ai_allowed."""
    if not bool(getattr(course, "chat_assistant_enabled", True)):
        return False
    vm = getattr(course, "visibility_mode", None) or "public"
    if vm == "public":
        return True
    if not student.study_group_id:
        return False
    acc = await session.scalar(
        select(CourseGroupAccess).where(
            CourseGroupAccess.course_id == course.id,
            CourseGroupAccess.study_group_id == student.study_group_id,
            CourseGroupAccess.problems_visible.is_(True),
            CourseGroupAccess.chat_ai_allowed.is_(True),
        )
    )
    return acc is not None


def _normalize_anti_cheat_mode(raw: str | None) -> Literal["off", "basic", "advanced"]:
    v = (raw or "advanced").strip().lower()
    if v in ("off", "basic", "advanced"):
        return v  # type: ignore[return-value]
    return "advanced"


async def _resolve_course_rag_context(
    request: Request, body: dict
) -> tuple[str, str, Literal["off", "basic", "advanced"]] | None:
    """
    Удаляет из тела bstu_course_id и/или bstu_course_slug (не уходит в OpenRouter),
    проверяет JWT преподавателя (владение курсом) или студента (доступ + чат) —
    имя коллекции Qdrant для RAG и slug курса (для anti-cheat по задачам).

    Корректировать контекст курса можно либо по UUID, либо по slug (slug — для совместимости,
    когда в ответе /api/public/my/courses ещё нет поля id).
    Нельзя передавать оба параметра одновременно.
    """
    raw_id = body.pop("bstu_course_id", None)
    raw_slug = body.pop("bstu_course_slug", None)
    have_id = raw_id not in (None, "")
    have_slug = raw_slug not in (None, "") and str(raw_slug).strip() != ""

    if not have_id and not have_slug:
        return None
    if have_id and have_slug:
        raise HTTPException(
            status_code=400,
            detail="Укажите только один параметр: bstu_course_id или bstu_course_slug.",
        )

    cfg = get_config()
    secret = getattr(cfg, "platform_jwt_secret", None)
    if not secret:
        raise HTTPException(status_code=500, detail="platform_jwt_secret not configured")

    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="RAG по курсу требует Authorization: Bearer JWT платформы")
    raw_tok = auth[7:].strip()
    if not _is_compact_jwt_payload(raw_tok):
        raise HTTPException(status_code=401, detail="Для контекста курса нужен JWT платформы (не ключ OpenRouter)")

    instructor_id = decode_instructor_id_from_jwt(raw_tok, secret)
    student_record_id = decode_student_id_from_jwt(raw_tok, secret)
    if instructor_id is None and student_record_id is None:
        raise HTTPException(status_code=401, detail="Invalid platform JWT")

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with factory() as session:
        row: Pcourse | None = None
        if have_id:
            try:
                course_uuid = uuid.UUID(str(raw_id).strip())
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid bstu_course_id") from None
            row = await session.get(Pcourse, course_uuid)
        else:
            if not _bstu_slug_param_ok(str(raw_slug)):
                raise HTTPException(status_code=400, detail="Invalid bstu_course_slug")
            slug_lc = str(raw_slug).strip().lower()
            row = await session.scalar(select(Pcourse).where(func.lower(Pcourse.slug) == slug_lc))

        if row is None:
            raise HTTPException(status_code=404, detail="Course not found")

        if instructor_id is not None:
            if row.instructor_id != instructor_id:
                raise HTTPException(status_code=404, detail="Course not found")
        else:
            st_row = await session.get(PlatformStudent, student_record_id)
            if st_row is None:
                raise HTTPException(status_code=401, detail="Invalid platform JWT")
            if not bool(getattr(row, "chat_assistant_enabled", True)):
                raise HTTPException(status_code=403, detail="Чат-ассистент для этого курса отключён.")
            if not await _student_may_use_course_chat_rag(session, st_row, row):
                raise HTTPException(status_code=403, detail="Чат с ИИ по этому курсу недоступен.")

        cn = (row.qdrant_collection_name or "").strip()
        slug = row.slug.strip().lower()
        mode = _normalize_anti_cheat_mode(getattr(row, "anti_cheat_mode", None))
        return (cn or course_collection_from_slug(row.slug), slug, mode)


@traceable(run_type="llm", name="openrouter_llm_proxy")
async def _call_openrouter(
    url: str,
    body: dict,
    headers: dict[str, str],
) -> dict:
    """Non-streaming LLM call to OpenRouter, traced as an LLM span."""
    async with httpx.AsyncClient(timeout=OPENROUTER_TIMEOUT_SECONDS) as client:
        response = await client.post(url, json=body, headers=headers)

    if response.status_code != 200:
        logger.error("OpenRouter error: status=%s, body=%s", response.status_code, response.text)
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text or "Upstream error",
        )
    return response.json()


# ── routes ─────────────────────────────────────────────────────────


@router.get("", summary="OpenAI API base")
@router.get("/", summary="OpenAI API base")
async def v1_root() -> dict[str, str | list[str]]:
    """OpenAI-совместимый API (прокси OpenRouter). Эндпоинты: /v1/models, /v1/chat/completions."""
    return {
        "message": "OpenAI-compatible API (OpenRouter proxy + optional RAG on chat)",
        "endpoints": ["/v1/models", "/v1/chat/completions"],
    }


def _is_compact_jwt_payload(token: str) -> bool:
    """Стандартный compact JWT (3 сегмента, JSON в заголовке) — платформа, не ключ OpenRouter."""
    parts = token.split(".")
    if len(parts) != 3:
        return False
    hdr_b64, _, sig = parts
    if len(hdr_b64) < 4 or len(sig) < 4:
        return False
    if not hdr_b64.startswith("eyJ"):
        return False
    pad = "=" * (-len(hdr_b64) % 4)
    try:
        hdr = json.loads(base64.urlsafe_b64decode(hdr_b64 + pad))
    except Exception:
        return False
    return isinstance(hdr, dict) and isinstance(hdr.get("alg"), str)


async def _get_auth_header(request: Request) -> str:
    """Bearer OpenRouter/sk-* — пробрасываем; JWT платформы / пусто — ключ из OPENROUTER_API_KEY."""
    try:
        server_key = get_openrouter_api_key()
    except ValueError:
        server_key = None

    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        raw = auth[7:].strip()
        if raw.startswith(("sk-or-", "sk-proj-")):
            return auth
        if _is_compact_jwt_payload(raw):
            if not server_key:
                raise HTTPException(
                    status_code=500,
                    detail="OPENROUTER_API_KEY not set — JWT сессию подставить в OpenRouter нельзя.",
                )
            return f"Bearer {server_key}"
        # Не JWT: возможно свой OpenRouter / legacy — пробуем как есть при наличии ключа-сервера нет ошибки upstream
        if raw:
            return auth

    if not server_key:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY not set. Set it in .env or pass Authorization: Bearer sk-or-…",
        )
    return f"Bearer {server_key}"


@router.get("/models", summary="Список моделей")
async def list_models(_request: Request) -> dict:
    """
    Список доступных моделей (OpenAI-совместимый формат).

    Возвращает сконфигурированную модель по умолчанию для OpenWebUI.
    """
    model = get_openrouter_model()
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "openrouter",
            }
        ],
    }


@router.post("/chat/completions", summary="Chat completions", response_model=None)
async def chat_completions(request: Request, bg: BackgroundTasks):
    """
    Chat completions (OpenAI-совместимый).

    Проксирует запросы в OpenRouter. Поддерживает streaming и обычный режим.
    При RAG_ENABLED: перед прокси — retrieval по последнему user-сообщению и инъекция контекста.
    """
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    original_messages = body.get("messages", [])

    rag_ctx = await _resolve_course_rag_context(request, body)
    rag_collection = rag_ctx[0] if rag_ctx else None
    course_slug = rag_ctx[1] if rag_ctx else None
    anti_cheat_mode = rag_ctx[2] if rag_ctx else "off"

    model = body.get("model") or get_openrouter_model()
    body["model"] = model

    cfg = get_config()
    if not cfg.enable_thinking:
        body["reasoning"] = {"effort": "none", "exclude": True}
    elif "reasoning" not in body:
        body["reasoning"] = {"effort": "high"}

    auth = await _get_auth_header(request)
    url = f"{OPENROUTER_BASE}/chat/completions"
    headers = _build_headers(auth, request)

    repo: ConversationRepository | None = getattr(request.app.state, "conversation_repo", None)

    stream = body.get("stream", False)

    rag_part = functools.partial(
        _apply_rag_to_chat_body,
        body,
        request,
        collection_override=rag_collection,
        course_slug=course_slug,
        anti_cheat_mode=anti_cheat_mode,
    )

    if stream:
        body = await asyncio.to_thread(rag_part)
        collected_text: list[str] = []

        async def stream_generator():
            async with httpx.AsyncClient(timeout=OPENROUTER_TIMEOUT_SECONDS) as client:
                async with client.stream(
                    "POST",
                    url,
                    json=body,
                    headers=headers,
                ) as response:
                    if response.status_code != 200:
                        err = await response.aread()
                        logger.error("OpenRouter stream error: %s %s", response.status_code, err)
                        yield f"data: {{\"error\": \"{response.status_code}\"}}\n\n"
                        return
                    async for chunk in response.aiter_bytes():
                        collected_text.append(chunk.decode("utf-8", errors="replace"))
                        yield chunk

            assistant_text = _extract_streaming_content(collected_text)

            with ls.trace(
                name="openrouter_llm_proxy",
                run_type="llm",
                inputs={"messages": body.get("messages", []), "model": model},
            ) as llm_rt:
                llm_rt.end(outputs={"content": assistant_text})

            if repo is not None:
                thread_id = derive_thread_id(original_messages)
                try:
                    await repo.save_turn(thread_id, original_messages, assistant_text)
                except Exception:
                    logger.exception("Failed to save streamed conversation turn")

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    # ── non-streaming path (fully traced) ──
    with ls.trace(
        name="rag_chat_completions",
        run_type="chain",
        inputs={"messages": original_messages, "model": model},
    ) as root_rt:
        body = await asyncio.to_thread(rag_part)

        try:
            data = await _call_openrouter(url, body, headers)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("OpenRouter request failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"Upstream error: {exc}")

        assistant_content = _extract_non_stream_content(data)
        root_rt.end(outputs={"content": assistant_content, "model": model})

    if repo is not None:
        thread_id = derive_thread_id(original_messages)
        bg.add_task(repo.save_turn, thread_id, original_messages, assistant_content)

    return JSONResponse(content=data)


@router.post("/completions", summary="Completions (legacy)")
async def completions(request: Request):
    """
    Legacy completions (OpenAI-совместимый).

    Проксирует в OpenRouter /v1/completions.
    """
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    model = body.get("model") or get_openrouter_model()
    body["model"] = model

    auth = await _get_auth_header(request)
    url = f"{OPENROUTER_BASE}/completions"

    async with httpx.AsyncClient(timeout=OPENROUTER_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(url, json=body, headers=_build_headers(auth))
        except Exception as exc:
            logger.error("OpenRouter completions failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"Upstream error: {exc}")

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=response.text or "Upstream error",
            )
        return JSONResponse(content=response.json())
