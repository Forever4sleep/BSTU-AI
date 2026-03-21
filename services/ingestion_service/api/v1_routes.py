"""
OpenAI-Compatible API Routes (v1)

Proxies requests to OpenRouter for OpenWebUI and other OpenAI-compatible clients.
Optional RAG: augments chat messages with Qdrant retrieval (see rag/ package).
"""

import asyncio
import copy
import json
import logging
import time

import httpx
import langsmith as ls
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langsmith import traceable

from config import get_config
from config.openrouter import (
    get_openrouter_api_key,
    get_openrouter_model,
)
from services.ingestion_service.db.repository import ConversationRepository, derive_thread_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["OpenAI-совместимый API"])

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_TIMEOUT_SECONDS = 120.0


# ── helpers ────────────────────────────────────────────────────────


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


def _apply_rag_to_chat_body(body: dict, request: Request) -> dict:
    """Deep-copy body and inject retrieved context into messages (sync; run in thread)."""
    cfg = get_config()
    if not cfg.rag_enabled:
        return body

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


async def _get_auth_header(request: Request) -> str:
    """Extract Bearer token from request, or use OpenRouter API key."""
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth
    try:
        api_key = get_openrouter_api_key()
    except ValueError:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY not set. Set it in .env or pass Authorization header.",
        )
    return f"Bearer {api_key}"


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

    if stream:
        body = await asyncio.to_thread(_apply_rag_to_chat_body, body, request)
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
        body = await asyncio.to_thread(_apply_rag_to_chat_body, body, request)

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
