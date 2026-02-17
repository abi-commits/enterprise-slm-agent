"""Document schemas for the Knowledge Service."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class UploadRequest(BaseModel):
    """Request schema for document upload."""

    title: str = Field(..., description="Document title")
    department: str = Field(..., description="Department the document belongs to")
    access_role: str = Field(default="all", description="Access role for RBAC (e.g., 'all', 'engineer', 'manager', 'admin')")
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


# ============================================================================
# Async Ingestion Schemas
# ============================================================================

class AsyncUploadResponse(BaseModel):
    """Response schema for async document upload (returns job ID for polling)."""

    job_id: str = Field(..., description="Job ID for status polling")
    document_id: str = Field(..., description="Document ID (will be used when completed)")
    status: str = Field(default="pending", description="Initial status (always 'pending')")
    message: str = Field(default="Document queued for processing", description="Status message")


class JobStatusResponse(BaseModel):
    """Response schema for job status polling."""

    job_id: str = Field(..., description="Job ID")
    document_id: str = Field(..., description="Associated document ID")
    status: str = Field(..., description="Job status: pending, processing, completed, failed, retrying")
    filename: str = Field(..., description="Original filename")
    title: str = Field(..., description="Document title")
    department: str = Field(..., description="Document department")
    chunks_created: int = Field(default=0, description="Number of chunks created (when completed)")
    processing_time_ms: float = Field(default=0.0, description="Processing time in milliseconds")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    retry_count: int = Field(default=0, description="Number of retry attempts")
    created_at: datetime = Field(..., description="Job creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# ============================================================================
# Bulk Upload Schemas
# ============================================================================

class BulkUploadItem(BaseModel):
    """Individual file status in bulk upload."""

    filename: str = Field(..., description="Original filename")
    job_id: Optional[str] = Field(None, description="Job ID for async processing")
    document_id: Optional[str] = Field(None, description="Document ID")
    status: str = Field(..., description="Status: queued, failed")
    error: Optional[str] = Field(None, description="Error message if failed")


class BulkUploadResponse(BaseModel):
    """Response schema for bulk document upload."""

    total_files: int = Field(..., description="Total number of files in upload")
    queued: int = Field(..., description="Number of files successfully queued")
    failed: int = Field(..., description="Number of files that failed to queue")
    items: list[BulkUploadItem] = Field(..., description="Status for each file")


class UploadResponse(BaseModel):
    """Response schema for document upload."""

    document_id: str = Field(..., description="Unique document ID")
    status: str = Field(..., description="Ingestion status (processing, completed, failed)")
    chunks_created: int = Field(..., description="Number of chunks created from the document")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")


class DocumentStatusResponse(BaseModel):
    """Response schema for document status check."""

    document_id: str = Field(..., description="Document ID")
    status: str = Field(..., description="Current status (processing, completed, failed)")
    chunks: int = Field(default=0, description="Number of chunks indexed")
    created_at: datetime = Field(..., description="Creation timestamp")
    title: Optional[str] = Field(None, description="Document title")
    department: Optional[str] = Field(None, description="Document department")
    access_role: Optional[str] = Field(None, description="Access role")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class DeleteRequest(BaseModel):
    """Request schema for document deletion."""

    document_id: str = Field(..., description="Document ID to delete")


class DeleteResponse(BaseModel):
    """Response schema for document deletion."""

    document_id: str = Field(..., description="Deleted document ID")
    status: str = Field(..., description="Deletion status")
    chunks_deleted: int = Field(..., description="Number of chunks deleted")


class DocumentListItem(BaseModel):
    """Schema for document list item."""

    document_id: str
    title: str
    department: str
    access_role: str
    chunks: int
    created_at: datetime
    status: str


class DocumentListResponse(BaseModel):
    """Response schema for document listing."""

    documents: list[DocumentListItem]
    total: int
