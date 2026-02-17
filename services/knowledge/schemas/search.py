"""Search schemas for the Knowledge Service."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Request schema for search endpoint."""

    query: str = Field(..., description="Search query text", min_length=1, max_length=1000)
    user_role: str = Field(..., description="User role for RBAC filtering")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")
    filters: Optional[dict[str, Any]] = Field(default=None, description="Additional filters for search")


class Document(BaseModel):
    """Document schema for search results."""

    id: str = Field(..., description="Document ID")
    content: str = Field(..., description="Document content")
    score: float = Field(..., description="Relevance score after reranking")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Document metadata")
    source: str = Field(..., description="Document source")


class SearchResponse(BaseModel):
    """Response schema for search endpoint."""

    results: list[Document] = Field(..., description="List of ranked documents")
    total: int = Field(..., description="Total number of results found")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
