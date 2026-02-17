"""Inference Service - Consolidated FastAPI application entry point.

This service consolidates the Query Optimizer and Generator services into
a single inference service. It uses Qwen-2.5 SLM for query optimization
and provides LLM-based answer generation with template fallback.

The service shares a single vLLM client between the optimizer and generator.
"""

import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config.settings import get_settings

from services.inference.generator import llm_client as llm_module
from services.inference.optimizer.model import get_model
from services.inference.routers import generate as generate_router
from services.inference.routers import optimize as optimize_router
from services.inference.schemas import HealthResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ],
)

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - handles startup and shutdown."""
    # Startup
    logger.info("Starting Inference Service...")
    logger.info(f"vLLM URL: {settings.vllm_url}")
    logger.info(f"Use vLLM: {settings.use_vllm}")
    logger.info(f"Model: {settings.llm_model}")

    # Initialize query optimizer model (lazy loading)
    try:
        model = await get_model()
        logger.info(f"Query optimizer model initialized: {model.model_name}")
        logger.info(f"vLLM available (optimizer): {model.is_vllm_available()}")
    except Exception as e:
        logger.error(f"Failed to initialize query optimizer model: {e}")

    # Test vLLM connection for generator
    logger.info("Testing vLLM connection for generator...")
    try:
        llm = llm_module.get_llm_client()
        vllm_healthy = await llm.check_vllm_health()
        if vllm_healthy:
            logger.info(f"vLLM connection successful at {settings.vllm_url}")
        else:
            logger.warning(
                f"vLLM connection failed at {settings.vllm_url} - "
                "generator will use template-based generation as fallback"
            )
    except Exception as e:
        logger.warning(f"vLLM connection error during startup: {e}")

    logger.info("Inference Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Inference Service...")

    # Close LLM client connections
    try:
        llm = llm_module.get_llm_client()
        await llm.close()
    except Exception as e:
        logger.warning(f"Error closing LLM client: {e}")


# Create FastAPI application
app = FastAPI(
    title="Inference Service",
    description=(
        "Consolidated Inference Service for Enterprise SLM-First Knowledge Copilot. "
        "Combines Query Optimization (Qwen-2.5 SLM) and Answer Generation (LLM/template)."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
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
app.include_router(
    optimize_router.router,
    prefix="/api/v1",
    tags=["Query Optimization"],
)
app.include_router(
    generate_router.router,
    tags=["Answer Generation"],
)


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check if the Inference Service is healthy",
)
async def health():
    """Health check endpoint checking vLLM and model status."""
    vllm_connected = False
    model_loaded = False
    model_name = settings.llm_model
    vllm_available = False

    # Check query optimizer model status
    try:
        model = await get_model()
        model_loaded = model.is_ready()
        model_name = model.model_name
        vllm_available = model.is_vllm_available()
    except Exception as e:
        logger.error(f"Health check - optimizer model error: {e}")

    # Check vLLM connection for generator
    try:
        llm = llm_module.get_llm_client()
        vllm_connected = await llm.check_vllm_health()
    except Exception as e:
        logger.error(f"Health check - vLLM connection error: {e}")

    # Determine overall status
    if model_loaded and vllm_connected:
        status_str = "healthy"
    elif model_loaded or vllm_connected:
        status_str = "degraded"
    else:
        status_str = "unhealthy"

    return HealthResponse(
        status=status_str,
        vllm_connected=vllm_connected,
        model_loaded=model_loaded,
        model_name=model_name,
        vllm_available=vllm_available,
    )


@app.get("/", summary="Root endpoint")
async def root():
    """Root endpoint - returns service info."""
    return {
        "service": "Inference Service",
        "version": "1.0.0",
        "description": "Consolidated Query Optimization and Answer Generation Service",
        "docs": "/docs",
    }


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_error",
            "message": "An internal error occurred",
            "detail": str(exc) if settings.debug else None,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.inference.main:app",
        host="0.0.0.0",
        port=8002,
        reload=settings.debug,
    )
