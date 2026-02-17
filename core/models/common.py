"""Common models shared across services."""

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class HealthCheck(BaseModel):
    """Health check response model."""

    status: str = Field(..., description="Service status")
    service: str = Field(..., description="Service name")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp")


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    request_id: Optional[str] = Field(None, description="Request ID for tracking")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Error timestamp"
    )


class BaseResponse(BaseModel, Generic[T]):
    """Generic base response model."""

    success: bool = Field(..., description="Whether the operation was successful")
    data: Optional[T] = Field(None, description="Response data")
    message: Optional[str] = Field(None, description="Optional message")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Response timestamp"
    )


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Page size")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response model."""

    items: list[T] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
