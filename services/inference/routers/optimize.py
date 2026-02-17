"""Query optimization endpoint for the Inference Service."""

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from services.inference.optimizer.model import get_model
from services.inference.schemas import OptimizeRequest, OptimizeResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/optimize",
    response_model=OptimizeResponse,
    summary="Optimize query",
    description="Optimize a user query using Qwen-2.5 SLM for better document retrieval",
    responses={
        200: {
            "description": "Successfully optimized query",
            "model": OptimizeResponse,
        },
        400: {
            "description": "Invalid request",
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_request",
                        "message": "Query is required and must be between 1 and 1000 characters",
                    }
                }
            },
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "error": "model_error",
                        "message": "Failed to optimize query",
                    }
                }
            },
        },
    },
)
async def optimize_query(request: OptimizeRequest) -> OptimizeResponse:
    """Optimize a query for better document retrieval.

    This endpoint uses Qwen-2.5 SLM to:
    - Expand and enrich user queries
    - Extract key keywords
    - Rephrase queries in multiple ways
    - Score confidence (0.0 to 1.0)

    Args:
        request: OptimizeRequest containing query and optional user_context

    Returns:
        OptimizeResponse with optimized queries, confidence, and keywords
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()

    logger.info(
        f"Request {request_id}: Optimizing query: {request.query[:100]}..."
    )

    try:
        # Validate query
        if not request.query or not request.query.strip():
            logger.warning(f"Request {request_id}: Empty query received")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query is required and must be between 1 and 1000 characters",
            )

        # Get the model
        model = await get_model()

        # Perform optimization
        result = await model.optimize_query(
            query=request.query,
            user_context=request.user_context,
        )

        # Calculate processing time
        processing_time_ms = (time.time() - start_time) * 1000

        # Log the result
        logger.info(
            f"Request {request_id}: Optimized successfully - "
            f"confidence={result.get('confidence', 0):.2f}, "
            f"keywords={len(result.get('keywords', []))}, "
            f"processing_time={processing_time_ms:.2f}ms"
        )

        # Build response
        response = OptimizeResponse(
            optimized_queries=result.get("optimized_queries", [request.query]),
            confidence=float(result.get("confidence", 0.5)),
            keywords=result.get("keywords", []),
            processing_time_ms=round(processing_time_ms, 2),
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Request {request_id}: Error optimizing query: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to optimize query: {str(e)}",
        )


@router.get(
    "/health",
    summary="Health check",
    description="Check if the query optimizer service is healthy",
)
async def health_check() -> JSONResponse:
    """Health check endpoint."""
    try:
        model = await get_model()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "healthy",
                "model_loaded": model.is_ready(),
                "model_name": model.model_name,
                "vllm_available": model.is_vllm_available(),
            },
        )
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "error": str(e),
            },
        )
