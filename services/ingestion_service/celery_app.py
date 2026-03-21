"""
Celery application for async document processing.
"""

from celery import Celery

from config import get_config


def make_celery() -> Celery:
    config = get_config()
    backend = config.celery_result_backend or config.celery_broker_url

    app = Celery(
        "ingestion",
        broker=config.celery_broker_url,
        backend=backend,
        include=["services.ingestion_service.tasks"],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        result_expires=86400,
        task_track_started=True,
    )
    return app


celery_app = make_celery()
