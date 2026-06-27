"""
API Schemas for Ingestion Service

Pydantic models for request/response.
"""

from typing import Any

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    """Ответ после принятия документа в обработку (асинхронно)."""

    success: bool = True
    message: str = "Документ принят в обработку"
    job_id: str = Field(..., description="ID задачи для проверки статуса")
    filename: str = Field(..., description="Имя файла")
    status: str = Field(default="pending", description="Статус: pending, processing, success, failure")


class BatchUploadResponse(BaseModel):
    """Ответ после принятия пакета документов в обработку."""

    files_queued: int = Field(..., description="Количество файлов в очереди")
    job_ids: list[str] = Field(
        default_factory=list,
        description="Список job_id для проверки статуса каждого файла",
    )
    message: str = "Документы приняты в обработку"


class JobStatusResponse(BaseModel):
    """Статус задачи обработки документа."""

    job_id: str = Field(..., description="ID задачи")
    status: str = Field(
        ...,
        description="Статус: PENDING, STARTED, SUCCESS, FAILURE",
    )
    filename: str | None = Field(default=None, description="Имя файла (если известно)")
    chunks_indexed: int | None = Field(
        default=None,
        description="Количество чанков (при успехе)",
    )
    collection: str | None = Field(default=None, description="Коллекция Qdrant (при успехе)")
    error: str | None = Field(default=None, description="Сообщение об ошибке (при failure)")


class ErrorResponse(BaseModel):
    """Схема ответа об ошибке."""

    success: bool = False
    message: str = Field(..., description="Сообщение об ошибке")
    detail: str | None = Field(default=None, description="Дополнительная информация")
