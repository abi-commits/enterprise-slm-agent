"""Context Engineering router.

Provides a standalone endpoint for transforming raw search results
into optimized context for LLM consumption.
"""

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from services.context_engine.context_optimizer import ContextOptimizer
from services.context_engine.schemas import (
    ContextConfig,
    ContextMetrics,
    ContextRequest,
    ContextResponse,
)

logger = __import__("core.logging").get_logger(__name__)

router = APIRouter(prefix="/context", tags=["context"])


def get_context_optimizer() -> ContextOptimizer:
    """Dependency to get the global ContextOptimizer instance."""
    # In a real app, this might be a singleton managed by the app state
    return ContextOptimizer()


@router.post("/engineer", response_model=ContextResponse)
async def engineer_context(
    request: ContextRequest,
    optimizer: ContextOptimizer = Depends(get_context_optimizer),
) -> ContextResponse:
    """
    Transform raw document results into optimized context.

    Accepts a list of documents (as returned from search) and applies
    token budgeting, truncation, deduplication, and template rendering
    to produce a final context string ready for an LLM.

    The endpoint can be called independently after a search, or
    the search endpoint will call it internally when context_engineering=True.
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()

    logger.info(
        f"Context engineering request {request_id}: "
        f"{len(request.documents)} docs, query='{request.query[:50]}...'"
    )

    try:
        # Validate documents
        if not request.documents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one document is required",
            )

        # Use provided config or default
        config = request.config or ContextConfig()

        # Perform optimization
        result = optimizer.optimize(
            documents=request.documents,
            query=request.query,
            keywords=request.keywords,
            user_role=request.user_role,
            conversation_history=request.conversation_history,
        )

        processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Context engineered {request_id}: "
            f"tokens={result.tokens_used}, "
            f"docs={result.documents_included}/{result.documents_original}, "
            f"time={processing_time_ms:.2f}ms"
        )

        # Build metrics object
        metrics = ContextMetrics(
            documents_included=result.documents_included,
            documents_original=result.documents_original,
            tokens_used=result.tokens_used,
            budget_remaining=result.budget_remaining,
            coverage_score=result.coverage_score,
            truncated_count=result.metadata.get("truncated_count", 0),
            deduplication_removed=result.metadata.get("deduplication_removed", 0),
        )

        return ContextResponse(
            formatted_context=result.formatted_context,
            metrics=metrics,
            config_used=config,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Context engineering failed for {request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context engineering failed: {str(e)}",
        ) from e
