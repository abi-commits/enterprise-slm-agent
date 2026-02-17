"""Query-related Pydantic schemas.

Schemas for query orchestration and clarification flow.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Query request schema."""

    query: str = Field(..., min_length=1, max_length=1000, description="User query")
    user_id: str = Field(..., description="User ID")
    session_id: Optional[str] = Field(None, description="Session ID for tracking")


class Source(BaseModel):
    """Source document schema."""

    document_id: str = Field(..., description="Document ID")
    title: Optional[str] = Field(None, description="Document title")
    content: str = Field(..., description="Source content excerpt")
    score: float = Field(..., description="Relevance score")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class QueryResponse(BaseModel):
    """Query response schema."""

    answer: str = Field(..., description="Generated answer")
    confidence: float = Field(..., description="Confidence score (0-1)")
    sources: List[Source] = Field(default_factory=list, description="Source documents")
    latency_ms: float = Field(..., description="Total latency in milliseconds")
    service_latencies: Optional[dict] = Field(
        None, description="Latency per service in milliseconds"
    )
    request_id: Optional[str] = Field(None, description="Request ID for tracing")


class ClarificationOption(BaseModel):
    """Clarification option schema."""

    text: str = Field(..., description="Clarification text")
    query: str = Field(..., description="Revised query option")


class ClarificationRequest(BaseModel):
    """Clarification request schema for low confidence queries."""

    message: str = Field(..., description="Message asking for clarification")
    options: List[ClarificationOption] = Field(..., description="Clarification options")
    confidence: float = Field(..., description="Original query confidence")
    original_query: str = Field(..., description="Original user query")


class ClarificationResponse(BaseModel):
    """Clarification response schema."""

    selected_option: Optional[str] = Field(None, description="Selected clarification option")
    revised_query: Optional[str] = Field(None, description="Revised query")
