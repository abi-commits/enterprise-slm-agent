"""Search schemas for the Context Engine Service."""

from typing import Any

from pydantic import BaseModel, Field

from .context import ContextConfig, ContextMetrics


class SearchRequest(BaseModel):
    """Request schema for search endpoint.

    Supports either a single query or multiple query variants for enhanced retrieval.
    """
    # Single query (original) OR multiple query variants
    query: str | None = Field(
        default=None,
        description="Single search query text (use if queries not provided)",
        min_length=1,
        max_length=1000,
    )
    queries: list[str] | None = Field(
        default=None,
        description="List of query variants for multi-query retrieval (e.g., from query optimizer)",
        min_length=1,
    )
    user_role: str = Field(..., description="User role for RBAC filtering")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")
    filters: dict[str, Any] | None = Field(default=None, description="Additional filters for search")
    # Context engineering options (optional)
    context_engineering: bool = Field(
        default=False,
        description="Enable context engineering on the search results"
    )
    context_config: "ContextConfig | None" = Field(
        default=None,
        description="Context optimization configuration"
    )
    # Additional data for context augmentation
    keywords: list[str] | None = Field(
        default=None,
        description="Extracted keywords to enhance context (from query optimizer)"
    )
    conversation_history: list[dict[str, str]] | None = Field(
        default=None,
        description="Previous conversation turns for multi-turn context"
    )

    def get_queries(self) -> list[str]:
        """Return the list of queries to process."""
        if self.queries:
            return self.queries
        if self.query:
            return [self.query]
        raise ValueError("Either query or queries must be provided")


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
    # Context engineering outputs (optional, only if context_engineering=True)
    engineered_context: str | None = Field(
        default=None,
        description="Fully engineered context string (if context_engineering enabled)"
    )
    context_metrics: "ContextMetrics | None" = Field(
        default=None,
        description="Metrics from context optimization (if context_engineering enabled)"
    )
