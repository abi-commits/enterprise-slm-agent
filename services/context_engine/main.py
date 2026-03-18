"""Context Engine Service - Combined FastAPI application (Search + Ingestion + Context Optimization).

This consolidated service merges the Search Engine, Document Ingestion, and Context
Optimization capabilities. It shares a single embedding model instance (BAAI/bge-small-en-v1.5),
Qdrant client, and now provides intelligent context engineering to optimize retrieved
documents for LLM consumption.

Supports both synchronous and asynchronous document ingestion via Redis Streams.
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from core.config.settings import get_settings
from core.logging import configure_logging, get_logger
from core.tracing import (
    configure_tracing,
    instrument_cache,
    instrument_fastapi,
    instrument_http_clients,
)
from services.context_engine import schemas as context_schemas
from services.context_engine.queue import IngestionWorker, get_queue
from services.context_engine.retrieval import embeddings as embedding_service
from services.context_engine.retrieval import reranker as reranker_service
from services.context_engine.retrieval import vector_store as qdrant_service
from services.context_engine.routers import documents as documents_router
from services.context_engine.routers import search as search_router
from services.context_engine.routers import context as context_router

# Configure structured logging
settings = get_settings()
configure_logging(
    log_level=settings.log_level,
    json_output=settings.environment != "development",
    service_name="context-engine-service",
)

# Configure distributed tracing
configure_tracing(
    service_name="context-engine-service",
    otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    environment=settings.environment,
    enabled=True,
)

logger = get_logger(__name__)

# Global worker reference
_ingestion_worker: IngestionWorker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    global _ingestion_worker
    settings = get_settings()

    # Startup
    logger.info("service_startup", service="context-engine-service")

    # Test Qdrant connection
    logger.info("Testing Qdrant connection...")
    try:
        qdrant_healthy = qdrant_service.check_qdrant_health()
        if qdrant_healthy:
            logger.info("Qdrant connection successful")
            # Create collection if it doesn't exist
            embedding_dim = embedding_service.get_embedding_dimension()
            qdrant_service.create_collection_if_not_exists(embedding_dim)
        else:
            logger.warning("Qdrant connection failed - service will retry on requests")
    except Exception as e:
        logger.warning(f"Qdrant connection error during startup: {e}")

    # Load embedding model (shared between search and ingestion)
    logger.info("Loading embedding model...")
    try:
        embedding_service.get_embedding_model()
        logger.info("Embedding model loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load embedding model: {e}")

    # Load reranker model
    logger.info("Loading reranker model...")
    try:
        reranker_service.get_reranker_model()
        logger.info("Reranker model loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load reranker model: {e}")

    # Connect to Redis queue and start ingestion worker
    logger.info("Connecting to Redis queue...")
    try:
        queue = get_queue()
        await queue.connect()
        logger.info("Redis queue connected")

        # Start ingestion worker
        _ingestion_worker = IngestionWorker(
            queue=queue,
            process_func=documents_router.process_document_sync,
            consumer_name=f"context-engine-worker-{settings.context_engine_service_port}",
        )
        await _ingestion_worker.start()
        logger.info("Ingestion worker started")
    except Exception as e:
        logger.warning(f"Failed to connect Redis queue: {e}. Async ingestion disabled.")

    logger.info("Context Engine Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Context Engine Service...")

    # Stop ingestion worker
    if _ingestion_worker:
        await _ingestion_worker.stop()
        logger.info("Ingestion worker stopped")

    # Disconnect queue
    try:
        queue = get_queue()
        await queue.disconnect()
        logger.info("Redis queue disconnected")
    except Exception:
        pass


# Create FastAPI application
app = FastAPI(
    title="Context Engine Service",
    description="Consolidated Search + Ingestion + Context Optimization service for Enterprise Knowledge Copilot. "
    "Provides vector search with RBAC, reranking, document upload, parsing, chunking, embedding, "
    "storage in Qdrant, and advanced context engineering for optimal LLM consumption.",
    version="1.0.0",
    lifespan=lifespan,
)

# Instrument FastAPI for distributed tracing
instrument_fastapi(app)

# Instrument HTTP clients for trace propagation
instrument_http_clients()

# Instrument cache operations
instrument_cache()

# Add CORS middleware
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log incoming requests with request ID for distributed tracing."""
    request_id = request.headers.get("X-Request-ID", "unknown")
    start_time = time.time()

    logger.info(
        f"Request started: {request.method} {request.url.path} "
        f"request_id={request_id}"
    )

    response = await call_next(request)

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        f"Request completed: {request.method} {request.url.path} "
        f"status={response.status_code} duration={elapsed_ms:.2f}ms "
        f"request_id={request_id}"
    )

    # Add request ID to response headers for tracing
    response.headers["X-Request-ID"] = request_id
    return response


# Include routers
app.include_router(search_router.router)
app.include_router(documents_router.router)
app.include_router(context_router.router)


@app.get("/health", response_model=context_schemas.HealthResponse)
async def health_check():
    """Health check endpoint.

    Returns:
        Health status of the service and its dependencies (Qdrant, embedding model, reranker).
    """
    # Check Qdrant
    qdrant_connected = qdrant_service.check_qdrant_health()

    # Check embedding model (simple check by trying to get dimension)
    embedding_model_loaded = False
    try:
        embedding_service.get_embedding_dimension()
        embedding_model_loaded = True
    except Exception:
        pass

    # Check reranker model
    reranker_model_loaded = False
    try:
        reranker_service.get_reranker_model()
        reranker_model_loaded = True
    except Exception:
        pass

    # Determine overall status
    status_str = "healthy" if (qdrant_connected and embedding_model_loaded and reranker_model_loaded) else "degraded"

    return context_schemas.HealthResponse(
        status=status_str,
        qdrant_connected=qdrant_connected,
        embedding_model_loaded=embedding_model_loaded,
        reranker_model_loaded=reranker_model_loaded,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.context_engine.main:app",
        host="0.0.0.0",
        port=8001,
        reload=get_settings().debug,
    )
