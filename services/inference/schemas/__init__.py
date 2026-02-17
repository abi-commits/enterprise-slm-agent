"""Schemas for the Inference Service.

Re-exports all schemas for backward compatibility.
"""

from services.inference.schemas.generate import (
    EscalationReason,
    GenerateRequest,
    GenerateResponse,
    GenerationMethod,
    StreamChunk,
    StreamingGenerateRequest,
    TokenUsage,
)
from services.inference.schemas.health import ErrorResponse, HealthResponse
from services.inference.schemas.optimize import OptimizeRequest, OptimizeResponse

__all__ = [
    # Optimize schemas
    "OptimizeRequest",
    "OptimizeResponse",
    # Generate schemas
    "GenerateRequest",
    "TokenUsage",
    "GenerateResponse",
    "GenerationMethod",
    "EscalationReason",
    # Streaming schemas
    "StreamingGenerateRequest",
    "StreamChunk",
    # Health/Error schemas
    "HealthResponse",
    "ErrorResponse",
]
