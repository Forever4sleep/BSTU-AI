#!/usr/bin/env python3
"""
Сброс данных по курсам в PostgreSQL (локально / dev).

По умолчанию: TRUNCATE courses CASCADE — удаляет строки из courses и всех связанных таблиц
(CASCADE по FK в PostgreSQL), структура таблиц сохраняется.

Режим --drop-table: DROP TABLE courses CASCADE — удаляет саму таблицу courses
(остальные таблицы могут остаться с «битым» course_id до ручной чистки).
После перезапуска ingestion-service сработает create_all и создаст пустую courses.

Использование:
  export INGESTION_DB_URL=postgresql+asyncpg://bstu:bstu_dev@localhost:5432/bstu_ai
  python scripts/reset_courses_db.py --yes

Docker:
  docker compose exec postgres psql -U bstu -d bstu_ai -c "TRUNCATE TABLE courses CASCADE;"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

try:
    import psycopg2
except ImportError:
    print("Нужен пакет psycopg2-binary (уже в requirements.txt).", file=sys.stderr)
    sys.exit(1)


def _sync_dsn(url: str) -> str:
    """postgresql+asyncpg://... -> postgresql://..."""
    u = urlparse(url.replace("postgresql+asyncpg", "postgresql", 1))
    if u.scheme not in ("postgresql", "postgres"):
        raise ValueError(f"Ожидался INGESTION_DB_URL с postgresql, получено: {u.scheme!r}")
    return urlunparse(u)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description="Очистка таблицы courses и связанных данных.")
    ap.add_argument(
        "--drop-table",
        action="store_true",
        help="Выполнить DROP TABLE courses CASCADE вместо TRUNCATE (опаснее для целостности).",
    )
    ap.add_argument(
        "--yes",
        action="store_true",
        help="Подтверждение без интерактива (обязательно).",
    )
    args = ap.parse_args()

    if not args.yes:
        print("Укажите --yes для выполнения (без отката).", file=sys.stderr)
        sys.exit(2)

    raw = os.environ.get("INGESTION_DB_URL", "").strip()
    if not raw:
        print("Задайте INGESTION_DB_URL в окружении или в .env", file=sys.stderr)
        sys.exit(2)

    dsn = _sync_dsn(raw)

    if args.drop_table:
        sql = "DROP TABLE IF EXISTS courses CASCADE;"
        warn = "DROP TABLE courses CASCADE — таблица удалена; при необходимости проверьте platform_problems и др."
    else:
        sql = "TRUNCATE TABLE courses CASCADE;"
        warn = "TRUNCATE courses CASCADE — все курсы и связанные строки по FK удалены; структура сохранена."

    conn = psycopg2.connect(dsn)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
        print(warn)
        print("OK.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
