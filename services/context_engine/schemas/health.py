"""Health check schemas for the Knowledge Service."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Unified health check response for the Knowledge Service."""

    status: str = Field(..., description="Service health status")
    qdrant_connected: bool = Field(..., description="Qdrant connection status")
    embedding_model_loaded: bool = Field(..., description="Embedding model status")
    reranker_model_loaded: bool = Field(..., description="Reranker model status")
