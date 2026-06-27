"""Upsert published problems into per-course Qdrant collections."""

from __future__ import annotations

import logging
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from services.ingestion_service.processing.embeddings import OpenRouterEmbeddings
from services.ingestion_service.problem_platform.qdrant_naming import course_problems_collection_from_slug
from services.ingestion_service.qdrant_client import create_qdrant_client, ensure_collection

logger = logging.getLogger(__name__)

_PROBLEM_TEXT_LIMIT = 1500


def problem_index_text(title: str, statement: str) -> str:
    stmt = (statement or "")[:_PROBLEM_TEXT_LIMIT]
    title = (title or "").strip()
    return f"{title}\n\n{stmt}" if stmt else title


def upsert_published_problem_to_qdrant(
    *,
    problem_id: uuid.UUID,
    title: str,
    statement: str,
    course_slug: str,
    client: QdrantClient | None = None,
) -> None:
    """Embed title+statement and upsert one point (ID = problem_id)."""
    qdrant = client or create_qdrant_client()
    col = course_problems_collection_from_slug(course_slug)
    ensure_collection(qdrant, collection_name=col)
    text = problem_index_text(title, statement)
    vec = OpenRouterEmbeddings().embed_documents([text])[0]
    qdrant.upsert(
        collection_name=col,
        points=[
            PointStruct(
                id=str(problem_id),
                vector=vec,
                payload={
                    "text": text,
                    "metadata": {
                        "problem_id": str(problem_id),
                        "title": title,
                    },
                },
            )
        ],
    )
    logger.info("Indexed problem %s in Qdrant collection %s", problem_id, col)


def scroll_course_problems(
    client: QdrantClient,
    collection_name: str,
    *,
    limit: int = 256,
) -> list[dict[str, str]]:
    """All indexed problems in course collection (id, title, text)."""
    if not collection_name.strip():
        return []
    rows: list[dict[str, str]] = []
    offset = None
    while True:
        records, offset = client.scroll(
            collection_name=collection_name.strip(),
            offset=offset,
            with_payload=True,
            with_vectors=False,
            limit=min(64, limit - len(rows)),
        )
        for record in records or []:
            pl = getattr(record, "payload", None) or {}
            meta = pl.get("metadata") if isinstance(pl.get("metadata"), dict) else {}
            problem_id = str(meta.get("problem_id") or "")
            title = str(meta.get("title") or "")
            text = str(pl.get("text") or "")
            if problem_id and text.strip():
                rows.append({"problem_id": problem_id, "title": title, "text": text.strip()})
            if len(rows) >= limit:
                break
        if offset is None or len(rows) >= limit:
            break
    return rows


def find_similar_problem(
    client: QdrantClient,
    collection_name: str,
    query_text: str,
    *,
    threshold: float,
) -> dict[str, str | float] | None:
    """Базовый античит: cosine similarity запроса к эмбеддингам опубликованных задач."""
    from services.ingestion_service.qdrant_client import search_similar_points

    cn = collection_name.strip()
    q = (query_text or "").strip()
    if not cn or not q:
        return None
    try:
        vec = OpenRouterEmbeddings().embed_documents([q])[0]
        hits = search_similar_points(client, collection_name=cn, vector=vec, limit=1)
    except Exception:
        logger.warning("find_similar_problem failed for collection %s", cn, exc_info=True)
        return None
    if not hits:
        return None
    top = hits[0]
    score = float(getattr(top, "score", 0.0) or 0.0)
    if score < threshold:
        return None
    pl = getattr(top, "payload", None) or {}
    meta = pl.get("metadata") if isinstance(pl.get("metadata"), dict) else {}
    problem_id = str(meta.get("problem_id") or getattr(top, "id", "") or "")
    title = str(meta.get("title") or "")
    if not problem_id:
        return None
    return {"problem_id": problem_id, "title": title or "задание курса", "score": score}


def delete_published_problem_from_qdrant(
    *,
    problem_id: uuid.UUID,
    course_slug: str,
    client: QdrantClient | None = None,
) -> None:
    """Remove one problem point from the course problems collection (best-effort)."""
    from qdrant_client.models import PointIdsList

    qdrant = client or create_qdrant_client()
    col = course_problems_collection_from_slug(course_slug)
    if not col.strip():
        return
    try:
        collections = {c.name for c in qdrant.get_collections().collections}
        if col not in collections:
            return
        qdrant.delete(
            collection_name=col,
            points_selector=PointIdsList(points=[str(problem_id)]),
        )
    except Exception:
        logger.warning("Failed to delete problem %s from Qdrant collection %s", problem_id, col, exc_info=True)
