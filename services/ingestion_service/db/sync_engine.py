"""Synchronous DB engine for Celery workers (asyncpg URLs → psycopg2)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def ingestion_sync_database_url(url: str) -> str:
    if "+asyncpg" in url:
        return url.replace("postgresql+asyncpg://", "postgresql://")
    return url


def create_sync_engine_from_config() -> tuple[object, sessionmaker[Session]]:
    from config import get_config

    url = get_config().ingestion_db_url
    if not url:
        raise ValueError("INGESTION_DB_URL is required for Celery catalog updates")
    sync_url = ingestion_sync_database_url(url)
    engine = create_engine(sync_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal
