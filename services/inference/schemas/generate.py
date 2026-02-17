"""Pydantic schemas for the Generator."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """Request schema for the generate endpoint.

    This endpoint is used for complex reasoning tasks and final answer
    generation when escalation is required from the query optimizer.
    """

    query: str = Field(
        ..., description="User query text", min_length=1, max_length=1000
    )
    context_documents: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of context documents from search results",
    )
    user_role: str = Field(..., description="User role for RBAC and context")
    use_llm: bool = Field(
        default=True,
        description="Whether to use LLM for generation (True) or simpler method (False)",
    )
    conversation_history: Optional[list[dict[str, str]]] = Field(
        default=None,
        description="Optional conversation history for context",
    )


class TokenUsage(BaseModel):
    """Token usage tracking for LLM requests."""

    prompt_tokens: int = Field(
        default=0, description="Number of tokens in the prompt"
    )
    completion_tokens: int = Field(
        default=0, description="Number of tokens in the completion"
    )
    total_tokens: int = Field(default=0, description="Total tokens used")


class GenerateResponse(BaseModel):
    """Response schema for the generate endpoint."""

    answer: str = Field(..., description="Generated answer text")
    tokens_used: int = Field(..., description="Total tokens used for generation")
    cost_usd: float = Field(..., description="Cost in USD for the generation")
    model_used: str = Field(..., description="Model used for generation")
    processing_time_ms: float = Field(
        ..., description="Processing time in milliseconds"
    )
    token_usage: TokenUsage = Field(
        ..., description="Detailed token usage breakdown"
    )


class GenerationMethod(str):
    """Generation method types."""

    LLM = "llm"
    TEMPLATE = "template"
    SLM = "slm"


class EscalationReason(str):
    """Reasons for escalation to LLM generation."""

    LOW_CONFIDENCE = "low_confidence"
    HIGH_RERANKER_AMBIGUITY = "high_reranker_ambiguity"
    HIGH_CONTEXT_COMPLEXITY = "high_context_complexity"
    EXPLICIT_REQUEST = "explicit_request"
    COMPLEX_REASONING = "complex_reasoning"


class StreamingGenerateRequest(BaseModel):
    """Request schema for streaming generate endpoint.
    
    Uses Server-Sent Events (SSE) to stream tokens as they're generated,
    providing better UX for long responses.
    """

    query: str = Field(
        ..., description="User query text", min_length=1, max_length=1000
    )
    context_documents: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of context documents from search results",
    )
    user_role: str = Field(..., description="User role for RBAC and context")
    max_tokens: int = Field(
        default=1024, 
        description="Maximum tokens to generate",
        ge=1,
        le=4096,
    )
    temperature: float = Field(
        default=0.7,
        description="Sampling temperature",
        ge=0.0,
        le=2.0,
    )


class StreamChunk(BaseModel):
    """Schema for a single SSE stream chunk."""
    
    token: str = Field(..., description="Generated token text")
    is_final: bool = Field(default=False, description="Whether this is the final chunk")
    finish_reason: Optional[str] = Field(None, description="Reason for completion")
