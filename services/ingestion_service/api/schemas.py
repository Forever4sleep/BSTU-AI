"""
API Schemas for Ingestion Service

Pydantic models for request/response.
"""

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    """Response after successful document upload and indexing."""

    success: bool = True
    message: str = "Document indexed successfully"
    chunks_indexed: int = Field(..., description="Number of chunks indexed")
    collection: str = Field(..., description="Qdrant collection name")
    filename: str = Field(..., description="Original filename")


class ErrorResponse(BaseModel):
    """Error response schema."""

    success: bool = False
    message: str = Field(..., description="Error message")
    detail: str | None = Field(default=None, description="Additional detail")
