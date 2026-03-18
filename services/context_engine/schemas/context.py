"""Schemas for Context Engineering functionality."""

from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator


class ContextConfig(BaseModel):
    """Configuration for context optimization.

    This can be passed in requests to customize behavior per-call.
    """
    max_tokens: int = Field(
        default=4096,
        ge=256,
        le=32768,
        description="Maximum tokens for the final context"
    )
    strategy: str = Field(
        default="smart_truncate",
        description="Truncation strategy: smart_truncate, selective, truncate"
    )
    include_metadata: bool = Field(
        default=True,
        description="Include document metadata in formatted context"
    )
    include_keywords: bool = Field(
        default=True,
        description="Include extracted keywords in context"
    )
    template_name: str = Field(
        default="default",
        description="Jinja2 template name (without .jinja2 extension)"
    )
    min_relevance_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum rerank score to include a document"
    )
    enable_deduplication: bool = Field(
        default=True,
        description="Remove duplicate or highly similar documents"
    )
    max_documents: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of documents to include"
    )

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        allowed = {"smart_truncate", "selective", "truncate"}
        if v not in allowed:
            raise ValueError(f"strategy must be one of {allowed}")
        return v


class ContextMetrics(BaseModel):
    """Metrics about the context optimization process."""
    documents_included: int = Field(..., description="Number of documents in final context")
    documents_original: int = Field(..., description="Number of input documents before optimization")
    tokens_used: int = Field(..., description="Token count of formatted context")
    budget_remaining: int = Field(..., description="Unused token budget")
    coverage_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Estimated query coverage (0.0-1.0)"
    )
    truncated_count: int = Field(
        default=0,
        description="Number of documents that were truncated"
    )
    deduplication_removed: int = Field(
        default=0,
        description="Number of duplicate documents removed"
    )


class ContextRequest(BaseModel):
    """Request for standalone context engineering."""
    query: str = Field(..., description="Original query for coverage estimation")
    documents: List[dict[str, Any]] = Field(..., description="List of raw search results")
    keywords: Optional[List[str]] = Field(default=None, description="Extracted keywords to include")
    user_role: Optional[str] = Field(default=None, description="User role for formatting")
    conversation_history: Optional[List[dict[str, str]]] = Field(
        default=None,
        description="Previous conversation turns"
    )
    config: Optional[ContextConfig] = Field(default=None, description="Override default config")


class ContextResponse(BaseModel):
    """Response from context engineering endpoint."""
    formatted_context: str = Field(..., description="Final optimized context string")
    metrics: ContextMetrics = Field(..., description="Optimization metrics")
    config_used: ContextConfig = Field(..., description="Config that was used")


# Extend existing Search schemas
# We'll add these fields to SearchResponse in the same module or via inheritance

EnhancedSearchResponse = None  # Will be created by modifying search schemas
