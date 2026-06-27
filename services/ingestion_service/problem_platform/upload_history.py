"""Файловая журнализация ошибок загрузки/индексации материалов курса."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def append_upload_failure(
    *,
    history_dir: Path,
    course_id: UUID | str | None,
    catalog_document_id: str | None,
    filename: str,
    job_id: str | None,
    error_message: str,
) -> None:
    try:
        history_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = history_dir / f"{day}_upload_failures.jsonl"
        rec: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "course_id": str(course_id) if course_id else None,
            "catalog_document_id": catalog_document_id,
            "filename": filename[:512],
            "job_id": job_id,
            "error": error_message[:16_384],
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("upload_history write failed")


def read_history_for_course(
    history_dir: Path,
    course_id: UUID,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if not history_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    cid = str(course_id)
    for path in sorted(history_dir.glob("*_upload_failures.jsonl"), reverse=True):
        try:
            with path.open(encoding="utf-8") as fh:
                for line in reversed(fh.readlines()):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("course_id") == cid:
                        out.append(obj)
                        if len(out) >= limit:
                            return out
        except OSError:
            continue
    return list(reversed(out))
