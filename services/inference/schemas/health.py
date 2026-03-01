"""Pydantic schemas for health and error responses."""


from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Unified health check response for the Inference Service."""

    status: str = Field(..., description="Service health status")
    vllm_connected: bool = Field(..., description="vLLM connection status")
    model_loaded: bool = Field(..., description="Whether the ML model is loaded")
    model_name: str | None = Field(None, description="Name of the loaded model")
    vllm_available: bool = Field(..., description="Whether vLLM is available")


class ErrorResponse(BaseModel):
    """Error response schema."""

    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    detail: str | None = Field(None, description="Additional error details")
