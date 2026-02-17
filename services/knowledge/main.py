"""Knowledge Service - Combined FastAPI application (Search + Ingestion).

This consolidated service merges the Search Engine and Document Ingestion services,
sharing a single embedding model instance (BAAI/bge-small-en-v1.5) and Qdrant client
across both search and ingestion operations.

Supports both synchronous and asynchronous document ingestion via Redis Streams.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from core.config.settings import get_settings
from services.knowledge.retrieval import embeddings as embedding_service
from services.knowledge.retrieval import reranker as reranker_service
from services.knowledge import schemas as knowledge_schemas
from services.knowledge.retrieval import vector_store as qdrant_service
from services.knowledge.routers import search as search_router
from services.knowledge.routers import documents as documents_router
from services.knowledge.queue import IngestionQueue, IngestionWorker, get_queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global worker reference
_ingestion_worker: IngestionWorker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    global _ingestion_worker
    settings = get_settings()

    # Startup
    logger.info("Starting Knowledge Service...")

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
            consumer_name=f"knowledge-worker-{settings.knowledge_service_port}",
        )
        await _ingestion_worker.start()
        logger.info("Ingestion worker started")
    except Exception as e:
        logger.warning(f"Failed to connect Redis queue: {e}. Async ingestion disabled.")

    logger.info("Knowledge Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Knowledge Service...")
    
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
    title="Knowledge Service",
    description="Consolidated Search + Ingestion service for Enterprise Knowledge Copilot. "
    "Provides vector search with RBAC and reranking, plus document upload, parsing, "
    "chunking, embedding, and storage in Qdrant.",
    version="1.0.0",
    lifespan=lifespan,
)

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


@app.get("/health", response_model=knowledge_schemas.HealthResponse)
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

    return knowledge_schemas.HealthResponse(
        status=status_str,
        qdrant_connected=qdrant_connected,
        embedding_model_loaded=embedding_model_loaded,
        reranker_model_loaded=reranker_model_loaded,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.knowledge.main:app",
        host="0.0.0.0",
        port=8001,
        reload=get_settings().debug,
    )
