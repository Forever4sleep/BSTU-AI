"""Docker healthcheck: broker reachable from Celery app (no HTTP on worker)."""

from services.ingestion_service.celery_app import celery_app


def main() -> None:
    conn = celery_app.connection()
    try:
        conn.ensure_connection(max_retries=2, timeout=5.0)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
