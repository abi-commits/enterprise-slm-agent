"""Core configuration settings using Pydantic BaseSettings."""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application Environment
    environment: str = Field(default="development", description="Application environment")
    debug: bool = Field(default=True, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # PostgreSQL Configuration
    postgres_user: str = Field(default="slm_user", description="PostgreSQL username")
    postgres_password: str = Field(default="slm_password", description="PostgreSQL password")
    postgres_db: str = Field(default="slm_knowledge", description="PostgreSQL database name")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    database_url: str = Field(
        default="postgresql+asyncpg://slm_user:slm_password@postgres:5432/slm_knowledge",
        description="Database connection URL (async)",
    )

    # Redis Configuration
    redis_port: int = Field(default=6379, description="Redis port")
    redis_url: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection URL",
    )

    # Qdrant Configuration
    qdrant_port: int = Field(default=6333, description="Qdrant REST port")
    qdrant_grpc_port: int = Field(default=6334, description="Qdrant gRPC port")
    qdrant_url: str = Field(
        default="http://qdrant:6333",
        description="Qdrant server URL",
    )
    qdrant_collection: str = Field(
        default="documents",
        description="Default Qdrant collection name",
    )

    # Service Ports (Consolidated: 3 services)
    api_service_port: int = Field(default=8000, description="API service port (Gateway + Auth + Metrics)")
    knowledge_service_port: int = Field(default=8001, description="Knowledge service port (Search + Ingestion)")
    inference_service_port: int = Field(default=8002, description="Inference service port (Query Optimizer + Generator)")

    # Service URLs (Internal - only for inter-service communication)
    knowledge_service_url: str = Field(
        default="http://knowledge-service:8000",
        description="Knowledge service URL (Search + Ingestion)",
    )
    inference_service_url: str = Field(
        default="http://inference-service:8000",
        description="Inference service URL (Query Optimizer + Generator)",
    )

    # Authentication & Security
    jwt_secret_key: str = Field(
        default="change-this-to-a-random-secret-key-in-production",
        description="JWT secret key for signing tokens",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(
        default=30, description="Access token expiration in minutes"
    )

    # ML Models
    embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="Embedding model name",
    )
    reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Reranker model name",
    )
    llm_model: str = Field(
        default="Qwen/Qwen2.5-1.5B-Instruct",
        description="LLM model name",
    )
    
    # vLLM Configuration
    vllm_url: str = Field(
        default="http://vllm:8000",
        description="vLLM inference server URL",
    )
    use_vllm: bool = Field(
        default=True,
        description="Use vLLM for inference (fallback to transformers)",
    )

    # Query Optimization
    confidence_threshold: float = Field(
        default=0.6,
        description="Confidence threshold for query routing",
    )

    # Rate Limiting
    rate_limit_requests: int = Field(
        default=100,
        description="Maximum requests per window",
    )
    rate_limit_window: int = Field(
        default=60,
        description="Rate limit window in seconds",
    )

    # Document Ingestion
    chunk_size: int = Field(default=512, description="Document chunk size in tokens")
    chunk_overlap: int = Field(default=50, description="Chunk overlap in tokens")
    max_file_size_mb: int = Field(
        default=50,
        description="Maximum file size in MB",
    )

    # Caching TTL (in seconds)
    cache_embedding_ttl: int = Field(
        default=86400,
        description="Embedding cache TTL (24 hours)",
    )
    cache_search_ttl: int = Field(
        default=3600,
        description="Search cache TTL (1 hour)",
    )
    cache_llm_response_ttl: int = Field(
        default=86400,
        description="LLM response cache TTL (24 hours)",
    )

    # Prometheus Metrics
    metrics_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_port: int = Field(default=9090, description="Prometheus metrics port")

    # OpenTelemetry
    otel_exporter_otlp_endpoint: Optional[str] = Field(
        default=None,
        description="OpenTelemetry OTLP exporter endpoint",
    )
    otel_service_name: str = Field(
        default="slm-knowledge-copilot",
        description="OpenTelemetry service name",
    )

    def get_sync_database_url(self) -> str:
        """Get synchronous database URL for migrations."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
