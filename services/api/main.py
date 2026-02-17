"""Consolidated API Service - FastAPI application entry point.

Combines Gateway + Auth + Metrics into a single service:
- Gateway: API entry point, request logging, rate limiting, caching
- Auth: JWT authentication and authorization (IN-PROCESS)
- Metrics: Prometheus metrics and audit logging (IN-PROCESS)

Only two external service dependencies remain:
- Knowledge Service (port 8001) for document search
- Inference Service (port 8002) for query optimization and answer generation
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config.settings import get_settings
from services.api.cache import cache_manager
from services.api.clients import service_clients
from services.api.database import db, init_db, close_db
from services.api.middleware import (
    close_rate_limit_redis,
    connect_rate_limit_redis,
    get_rate_limit_redis,
    log_requests,
    rate_limit_middleware,
)
from services.api.routers import auth_router, audit_router, metrics_router, query_router
from services.api.routers.metrics import prometheus_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler for startup and shutdown.

    Startup:
    - Connect auth DB (asyncpg pool for user queries)
    - Initialize metrics DB (SQLAlchemy tables for metrics/audit)
    - Connect Redis for caching
    - Connect Redis for rate limiting

    Shutdown:
    - Disconnect auth DB
    - Close metrics DB
    - Disconnect Redis cache
    - Close rate limiting Redis
    - Close service clients
    """
    # Startup
    logger.info("Starting API Service...")

    # Connect auth database (asyncpg)
    try:
        await db.connect()
        logger.info("Auth database (asyncpg) connected")
    except Exception as e:
        logger.error(f"Failed to connect auth database: {e}")

    # Initialize metrics database (SQLAlchemy)
    try:
        await init_db()
        logger.info("Metrics database (SQLAlchemy) initialized")
    except Exception as e:
        logger.error(f"Failed to initialize metrics database: {e}")

    # Connect to Redis for caching
    await cache_manager.connect()

    # Connect to Redis for rate limiting
    try:
        await connect_rate_limit_redis()
    except Exception as e:
        logger.error(f"Failed to connect to Redis for rate limiting: {e}")

    logger.info("API Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down API Service...")

    # Disconnect auth database
    await db.disconnect()
    logger.info("Auth database disconnected")

    # Close metrics database
    await close_db()
    logger.info("Metrics database closed")

    # Disconnect from Redis cache
    await cache_manager.disconnect()

    # Close rate limiting Redis
    await close_rate_limit_redis()

    # Close service clients
    await service_clients.close_all()

    logger.info("API Service shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="API Service",
    description="Enterprise SLM-First Knowledge Copilot - Consolidated API Service (Gateway + Auth + Metrics)",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware (from gateway)
@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    """Log all incoming requests with timing."""
    return await log_requests(request, call_next)


# Rate limiting middleware (from gateway)
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Rate limiting middleware using Redis."""
    return await rate_limit_middleware(request, call_next)


# Include routers
app.include_router(auth_router)
app.include_router(query_router)
app.include_router(metrics_router)
app.include_router(audit_router)

# Mount Prometheus metrics endpoint at /metrics/prometheus
# (to avoid conflict with the /metrics REST router)
app.mount("/metrics/prometheus", prometheus_app)


# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Basic health check endpoint for load balancers.

    Returns:
        Simple health status of the API Service.
    """
    return {
        "status": "healthy",
        "service": "api-service",
    }


@app.get("/health/aggregate")
async def health_check_aggregate():
    """
    Aggregated health check endpoint that checks all service dependencies.

    Provides comprehensive health status including:
    - Database connections (auth DB, metrics DB)
    - Redis cache and rate limiting
    - Downstream services (Knowledge, Inference)
    - Circuit breaker status

    Returns:
        Detailed health status of all components with individual check results.
    """
    import asyncio
    import time
    
    start_time = time.time()
    checks = {}
    overall_status = "healthy"
    
    # Check auth database (SQLAlchemy)
    try:
        from services.api.database import db_manager
        async with db_manager.session() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        checks["auth_db"] = {"status": "healthy", "type": "postgresql"}
    except Exception as e:
        checks["auth_db"] = {"status": "unhealthy", "error": str(e)}
        overall_status = "degraded"
    
    # Check Redis (cache)
    try:
        from services.api.cache import cache_manager
        if cache_manager._redis:
            await cache_manager._redis.ping()
            checks["redis_cache"] = {"status": "healthy"}
        else:
            checks["redis_cache"] = {"status": "unhealthy", "error": "Not connected"}
            overall_status = "degraded"
    except Exception as e:
        checks["redis_cache"] = {"status": "unhealthy", "error": str(e)}
        overall_status = "degraded"
    
    # Check Redis (rate limiting)
    try:
        redis_client = await get_rate_limit_redis()
        if redis_client:
            await redis_client.ping()
            checks["redis_rate_limit"] = {"status": "healthy"}
        else:
            checks["redis_rate_limit"] = {"status": "unhealthy", "error": "Not connected"}
            overall_status = "degraded"
    except Exception as e:
        checks["redis_rate_limit"] = {"status": "unhealthy", "error": str(e)}
        overall_status = "degraded"
    
    # Check Knowledge Service
    try:
        knowledge_client = service_clients.get_knowledge_client()
        response = await knowledge_client.get("/health")
        if response and response.get("status") == "healthy":
            checks["knowledge_service"] = {
                "status": "healthy",
                "url": knowledge_client.base_url,
                "circuit_breaker": knowledge_client.circuit_breaker.state.value,
            }
        else:
            checks["knowledge_service"] = {
                "status": "degraded",
                "url": knowledge_client.base_url,
                "response": response,
                "circuit_breaker": knowledge_client.circuit_breaker.state.value,
            }
            overall_status = "degraded"
    except Exception as e:
        knowledge_client = service_clients.get_knowledge_client()
        checks["knowledge_service"] = {
            "status": "unhealthy",
            "error": str(e),
            "circuit_breaker": knowledge_client.circuit_breaker.state.value,
        }
        overall_status = "degraded"
    
    # Check Inference Service
    try:
        inference_client = service_clients.get_inference_client()
        response = await inference_client.get("/health")
        if response and response.get("status") == "healthy":
            checks["inference_service"] = {
                "status": "healthy",
                "url": inference_client.base_url,
                "circuit_breaker": inference_client.circuit_breaker.state.value,
            }
        else:
            checks["inference_service"] = {
                "status": "degraded",
                "url": inference_client.base_url,
                "response": response,
                "circuit_breaker": inference_client.circuit_breaker.state.value,
            }
            overall_status = "degraded"
    except Exception as e:
        inference_client = service_clients.get_inference_client()
        checks["inference_service"] = {
            "status": "unhealthy",
            "error": str(e),
            "circuit_breaker": inference_client.circuit_breaker.state.value,
        }
        overall_status = "degraded"
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    return {
        "status": overall_status,
        "service": "api-service",
        "checks": checks,
        "check_duration_ms": round(elapsed_ms, 2),
        "timestamp": time.time(),
    }


# Global exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An internal server error occurred",
            "detail": str(exc) if settings.debug else None,
        },
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """404 error handler."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": "not_found",
            "message": f"Endpoint {request.url.path} not found",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
