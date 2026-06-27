"""Async SQLAlchemy engine and session factory."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import get_config
from services.ingestion_service.db.models import Base

logger = logging.getLogger(__name__)


def _pg_quote_ident(ident: str) -> str:
    """Кавычки для идентификатора из pg_catalog (только буквы, цифры, _)."""
    if not ident or not all(c.isalnum() or c == "_" for c in ident):
        raise ValueError(f"unsafe PostgreSQL identifier: {ident!r}")
    return f'"{ident}"'


def _ensure_instructors_auth_columns(sync_conn) -> None:
    """Добавить колонки логина к старым БД (create_all не делает ALTER).

    Ищем все физические таблицы instructors по pg_catalog — не только public,
    т.к. search_path и create_all могли создать таблицу в другой схеме.
    """
    rows = sync_conn.execute(
        text(
            """
            SELECT n.nspname::text
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'instructors'
              AND c.relkind = 'r'
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY n.nspname
            """
        )
    ).all()
    if not rows:
        logger.warning("DB migrate: no instructors table in pg_catalog — skip instructor auth columns")
        return

    for (schema,) in rows:
        try:
            qschema = _pg_quote_ident(schema)
        except ValueError:
            logger.warning("DB migrate: skip instructors in schema with odd name %r", schema)
            continue

        fq_table = f"{qschema}.instructors"
        sync_conn.execute(
            text(f"ALTER TABLE {fq_table} ADD COLUMN IF NOT EXISTS username VARCHAR(64)")
        )
        sync_conn.execute(
            text(f"ALTER TABLE {fq_table} ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)")
        )
        logger.info("DB migrate: %s.instructors username/password_hash ensured", schema)

        sync_conn.execute(text("SAVEPOINT sp_instructor_auth_idx"))
        try:
            sync_conn.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS ix_instructors_username "
                    f"ON {fq_table} (username)"
                )
            )
            sync_conn.execute(text("RELEASE SAVEPOINT sp_instructor_auth_idx"))
            logger.info("DB migrate: unique index on %s.instructors(username) ensured", schema)
        except Exception:
            sync_conn.execute(text("ROLLBACK TO SAVEPOINT sp_instructor_auth_idx"))
            logger.warning(
                "DB migrate: could not create unique index on %s.instructors (duplicate usernames?)",
                schema,
                exc_info=True,
            )


def _table_schemas(sync_conn, relname: str) -> list[str]:
    rows = sync_conn.execute(
        text(
            """
            SELECT n.nspname::text
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = :rel
              AND c.relkind = 'r'
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY n.nspname
            """
        ),
        {"rel": relname},
    ).all()
    return [r[0] for r in rows]


def _ensure_cabinet_columns(sync_conn) -> None:
    """Личный кабинет: ФИО преподавателя, режим видимости курса для студентов."""
    for schema in _table_schemas(sync_conn, "instructors"):
        try:
            q = _pg_quote_ident(schema)
        except ValueError:
            continue
        sync_conn.execute(
            text(
                f"ALTER TABLE {q}.instructors "
                f"ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)"
            )
        )
        logger.info("DB migrate: %s.instructors.full_name ensured", schema)

    for schema in _table_schemas(sync_conn, "courses"):
        try:
            q = _pg_quote_ident(schema)
        except ValueError:
            continue
        sync_conn.execute(
            text(
                f"ALTER TABLE {q}.courses "
                f"ADD COLUMN IF NOT EXISTS visibility_mode VARCHAR(24) DEFAULT 'public'"
            )
        )
        sync_conn.execute(
            text(
                f"ALTER TABLE {q}.courses "
                f"ADD COLUMN IF NOT EXISTS chat_assistant_enabled BOOLEAN DEFAULT TRUE"
            )
        )
        sync_conn.execute(
            text(
                f"ALTER TABLE {q}.courses "
                f"ADD COLUMN IF NOT EXISTS anti_cheat_mode VARCHAR(16) DEFAULT 'advanced'"
            )
        )
        logger.info("DB migrate: %s.courses.visibility_mode ensured", schema)


def _migrate_global_study_org(sync_conn) -> None:
    """Группы/студенты платформы: nullable instructor_id, глобальный уникальный access_key."""
    sg_schemas = set(_table_schemas(sync_conn, "study_groups"))
    ps_schemas = set(_table_schemas(sync_conn, "platform_students"))
    for schema in sorted(sg_schemas | ps_schemas):
        try:
            q = _pg_quote_ident(schema)
        except ValueError:
            continue
        fq_sg = f"{q}.study_groups"
        fq_ps = f"{q}.platform_students"
        fq_inst = f"{q}.instructors"

        if schema in sg_schemas:
            sync_conn.execute(text(f"ALTER TABLE {fq_sg} DROP CONSTRAINT IF EXISTS study_groups_instructor_id_fkey"))
            sync_conn.execute(text(f"ALTER TABLE {fq_sg} ALTER COLUMN instructor_id DROP NOT NULL"))
            sync_conn.execute(text("SAVEPOINT sp_sg_fkey"))
            try:
                sync_conn.execute(
                    text(
                        f"ALTER TABLE {fq_sg} ADD CONSTRAINT study_groups_instructor_id_fkey "
                        f"FOREIGN KEY (instructor_id) REFERENCES {fq_inst}(id) ON DELETE SET NULL"
                    )
                )
                sync_conn.execute(text("RELEASE SAVEPOINT sp_sg_fkey"))
                logger.info("DB migrate: %s study_groups.instructor_id → nullable + SET NULL", schema)
            except Exception:
                sync_conn.execute(text("ROLLBACK TO SAVEPOINT sp_sg_fkey"))
                logger.warning("DB migrate: study_groups FK not recreated", exc_info=True)

        if schema in ps_schemas:
            sync_conn.execute(text(f"ALTER TABLE {fq_ps} DROP CONSTRAINT IF EXISTS platform_students_instructor_id_fkey"))
            sync_conn.execute(text(f"ALTER TABLE {fq_ps} ALTER COLUMN instructor_id DROP NOT NULL"))
            sync_conn.execute(text("SAVEPOINT sp_ps_fkey"))
            try:
                sync_conn.execute(
                    text(
                        f"ALTER TABLE {fq_ps} ADD CONSTRAINT platform_students_instructor_id_fkey "
                        f"FOREIGN KEY (instructor_id) REFERENCES {fq_inst}(id) ON DELETE SET NULL"
                    )
                )
                sync_conn.execute(text("RELEASE SAVEPOINT sp_ps_fkey"))
                logger.info("DB migrate: %s platform_students.instructor_id → nullable + SET NULL", schema)
            except Exception:
                sync_conn.execute(text("ROLLBACK TO SAVEPOINT sp_ps_fkey"))
                logger.warning("DB migrate: platform_students FK not recreated", exc_info=True)

            sync_conn.execute(
                text(f"ALTER TABLE {fq_ps} DROP CONSTRAINT IF EXISTS uq_platform_student_instr_access_key")
            )
            sync_conn.execute(text("SAVEPOINT sp_ux_student_key"))
            try:
                sync_conn.execute(
                    text(f"ALTER TABLE {fq_ps} ADD CONSTRAINT uq_platform_student_access_key UNIQUE (access_key)")
                )
                sync_conn.execute(text("RELEASE SAVEPOINT sp_ux_student_key"))
                logger.info("DB migrate: %s.platform_students UNIQUE(access_key) ensured", schema)
            except Exception:
                sync_conn.execute(text("ROLLBACK TO SAVEPOINT sp_ux_student_key"))
                logger.info(
                    "DB migrate: UNIQUE(access_key) already present or duplicates — оставляем как есть",
                )


def _ensure_platform_admins_table(sync_conn) -> None:
    schemas = set(_table_schemas(sync_conn, "instructors")) | set(_table_schemas(sync_conn, "platform_students"))
    if not schemas:
        schemas.add("public")
    for schema in sorted(schemas):
        try:
            q = _pg_quote_ident(schema)
        except ValueError:
            continue
        fq = f"{q}.platform_admins"
        sync_conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {fq} (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  username VARCHAR(64) NOT NULL,
                  password_hash VARCHAR(255) NOT NULL,
                  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (timezone('utc', now()))
                )
                """
            )
        )
        sync_conn.execute(text("SAVEPOINT sp_pad_uq"))
        try:
            sync_conn.execute(
                text(f"CREATE UNIQUE INDEX IF NOT EXISTS ix_platform_admins_username ON {fq} (username)")
            )
            sync_conn.execute(text("RELEASE SAVEPOINT sp_pad_uq"))
        except Exception:
            sync_conn.execute(text("ROLLBACK TO SAVEPOINT sp_pad_uq"))
            logger.warning("DB migrate: platform_admins unique index skipped", exc_info=True)
        logger.info("DB migrate: %s.platform_admins table ensured", schema)


def _ensure_student_auth_columns(sync_conn) -> None:
    """Логин и пароль студента (JWT + опционально ключ как раньше)."""
    for schema in _table_schemas(sync_conn, "platform_students"):
        try:
            q = _pg_quote_ident(schema)
        except ValueError:
            continue
        fq = f"{q}.platform_students"
        sync_conn.execute(text(f"ALTER TABLE {fq} ADD COLUMN IF NOT EXISTS username VARCHAR(64)"))
        sync_conn.execute(text(f"ALTER TABLE {fq} ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)"))
        sync_conn.execute(text(f"ALTER TABLE {fq} ADD COLUMN IF NOT EXISTS avatar_ext VARCHAR(12)"))
        logger.info("DB migrate: %s.platform_students username/password_hash ensured", schema)
        sync_conn.execute(text("SAVEPOINT sp_stu_uname"))
        try:
            sync_conn.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS ix_platform_students_username "
                    f"ON {fq} (username)"
                )
            )
            sync_conn.execute(text("RELEASE SAVEPOINT sp_stu_uname"))
        except Exception:
            sync_conn.execute(text("ROLLBACK TO SAVEPOINT sp_stu_uname"))
            logger.warning(
                "DB migrate: index on %s.platform_students(username) skipped (duplicates/null?)",
                schema,
                exc_info=True,
            )


def _ensure_platform_problem_columns(sync_conn) -> None:
    """Поля сложности, лимита попыток и политики оценки для platform_problems."""
    for schema in _table_schemas(sync_conn, "platform_problems"):
        try:
            q = _pg_quote_ident(schema)
        except ValueError:
            continue
        fq = f"{q}.platform_problems"
        sync_conn.execute(text(f"ALTER TABLE {fq} ADD COLUMN IF NOT EXISTS difficulty INTEGER"))
        sync_conn.execute(text(f"ALTER TABLE {fq} ADD COLUMN IF NOT EXISTS max_attempts INTEGER"))
        sync_conn.execute(
            text(
                f"ALTER TABLE {fq} ADD COLUMN IF NOT EXISTS score_policy VARCHAR(16) "
                f"DEFAULT 'best'"
            )
        )
        logger.info("DB migrate: %s.platform_problems difficulty/max_attempts/score_policy ensured", schema)


def _ensure_platform_extra_columns(sync_conn) -> None:
    for schema in _table_schemas(sync_conn, "courses"):
        try:
            q = _pg_quote_ident(schema)
        except ValueError:
            continue
        sync_conn.execute(
            text(
                f"ALTER TABLE {q}.courses "
                f"ADD COLUMN IF NOT EXISTS qdrant_collection_name VARCHAR(255)"
            )
        )
        logger.info("DB migrate: %s.courses.qdrant_collection_name ensured", schema)

    for schema in _table_schemas(sync_conn, "documents_catalog"):
        try:
            q = _pg_quote_ident(schema)
        except ValueError:
            continue
        sync_conn.execute(
            text(
                f"ALTER TABLE {q}.documents_catalog "
                f"ADD COLUMN IF NOT EXISTS storage_relpath VARCHAR(512)"
            )
        )
        logger.info("DB migrate: %s.documents_catalog.storage_relpath ensured", schema)


def _backfill_course_qdrant_collections(sync_conn) -> None:
    from services.ingestion_service.problem_platform.qdrant_naming import (
        course_collection_from_slug,
    )
    from services.ingestion_service.qdrant_client import create_qdrant_client, ensure_collection

    client = create_qdrant_client()
    for schema in _table_schemas(sync_conn, "courses"):
        try:
            q = _pg_quote_ident(schema)
        except ValueError:
            continue
        rows = sync_conn.execute(
            text(f"SELECT id::text, slug, qdrant_collection_name FROM {q}.courses")
        ).fetchall()
        for rid, slug, existing in rows:
            col = (existing or "").strip() or course_collection_from_slug(slug)
            ensure_collection(client, collection_name=col)
            if not (existing or "").strip():
                sync_conn.execute(
                    text(
                        f"UPDATE {q}.courses SET qdrant_collection_name = :col "
                        f"WHERE id = CAST(:id AS uuid)"
                    ),
                    {"col": col, "id": rid},
                )
                logger.info("DB migrate: course %s → Qdrant collection %s", rid, col)


def create_db_engine(url: str | None = None) -> AsyncEngine:
    db_url = url or get_config().ingestion_db_url
    if not db_url:
        raise ValueError("INGESTION_DB_URL is not set in .env")
    return create_async_engine(db_url, echo=False, pool_size=5, max_overflow=10)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create tables if they don't exist."""
    import services.ingestion_service.db.problem_models  # noqa: F401 — register platform tables on Base.metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        await conn.run_sync(_ensure_instructors_auth_columns)

    async with engine.begin() as conn:
        await conn.run_sync(_ensure_platform_extra_columns)
        await conn.run_sync(_ensure_platform_problem_columns)
        await conn.run_sync(_ensure_cabinet_columns)
        await conn.run_sync(_migrate_global_study_org)
        await conn.run_sync(_ensure_platform_admins_table)
        await conn.run_sync(_ensure_student_auth_columns)
        await conn.run_sync(_backfill_course_qdrant_collections)

    logger.info("Database tables ensured")
