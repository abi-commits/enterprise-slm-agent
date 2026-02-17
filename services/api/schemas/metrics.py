"""Metrics and audit-related Pydantic schemas.

Schemas for metric recording, audit logging, and metrics summaries.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MetricRequest(BaseModel):
    """Schema for incoming metric data."""

    user_id: str = Field(..., description="User identifier")
    query: str = Field(..., description="User query")
    query_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score from optimizer"
    )
    branch_taken: str = Field(
        ..., description="Branch taken: 'slm' or 'llm'"
    )
    escalation_flag: bool = Field(
        ..., description="Whether the request was escalated to LLM"
    )
    latency_per_service: Optional[Dict[str, float]] = Field(
        default=None, description="Latency per service in milliseconds"
    )
    token_usage: Optional[Dict[str, int]] = Field(
        default=None,
        description="Token usage breakdown",
        examples=[{"prompt_tokens": 100, "completion_tokens": 50}],
    )
    response_time_ms: float = Field(
        ..., ge=0.0, description="Total response time in milliseconds"
    )


class MetricResponse(BaseModel):
    """Schema for metric response."""

    success: bool = Field(..., description="Whether the metric was stored successfully")
    message: str = Field(..., description="Response message")
    metric_id: Optional[int] = Field(default=None, description="Stored metric ID")


class AuditLogEntry(BaseModel):
    """Schema for a single audit log entry."""

    id: int = Field(..., description="Audit log ID")
    user_id: str = Field(..., description="User identifier")
    action: str = Field(..., description="Action performed")
    resource_type: str = Field(..., description="Type of resource accessed")
    resource_id: Optional[str] = Field(default=None, description="Resource identifier")
    details: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional details"
    )
    ip_address: Optional[str] = Field(default=None, description="Client IP address")
    user_agent: Optional[str] = Field(default=None, description="Client user agent")
    timestamp: datetime = Field(..., description="Timestamp of the action")


class AuditLogResponse(BaseModel):
    """Schema for audit log list response."""

    logs: List[AuditLogEntry] = Field(..., description="List of audit log entries")
    total: int = Field(..., description="Total number of matching logs")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


class AuditLogFilter(BaseModel):
    """Schema for audit log filtering."""

    user_id: Optional[str] = Field(default=None, description="Filter by user ID")
    action: Optional[str] = Field(default=None, description="Filter by action")
    resource_type: Optional[str] = Field(
        default=None, description="Filter by resource type"
    )
    start_date: Optional[datetime] = Field(
        default=None, description="Filter by start date"
    )
    end_date: Optional[datetime] = Field(default=None, description="Filter by end date")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(
        default=50, ge=1, le=100, description="Number of items per page"
    )


class MetricsSummary(BaseModel):
    """Summary of key metrics."""

    total_requests: int = Field(..., description="Total requests processed")
    llm_escalation_rate: float = Field(..., description="LLM escalation rate (%)")
    avg_response_time_ms: float = Field(
        ..., description="Average response time in ms"
    )
    active_users: int = Field(..., description="Number of active users")
    cost_accumulated_usd: float = Field(..., description="Accumulated cost in USD")
    cost_saved_vs_llm: float = Field(
        ..., description="Cost saved vs LLM-only baseline"
    )
