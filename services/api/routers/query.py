"""Query router for the consolidated API Service.

Adapted from services/gateway/routers/query.py with key changes:
- Token validation is IN-PROCESS via core.security.jwt.verify_token
  (no HTTP call to auth service)
- Search calls go to knowledge service via service_client
- Generate calls go to inference service via service_client
- Metrics recording is IN-PROCESS via database.store_metric and
  prometheus functions (no HTTP call to metrics service)
"""

import logging
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.config.settings import get_settings
from services.api.cache import CacheManager, get_cache
from services.api.clients import ServiceClientFactory, service_clients, set_current_request_id
from services.api.database import (
    engine,
    store_metric,
    store_audit_log,
)
from services.api.routers.auth import get_current_user
from services.api.schemas import (
    ClarificationRequest,
    ClarificationResponse,
    QueryRequest,
    QueryResponse,
    Source,
    ValidateTokenResponse,
)
from services.api import prometheus

logger = logging.getLogger(__name__)

settings = get_settings()

router = APIRouter(prefix="/query", tags=["query"])


async def track_latency(
    service_name: str,
    start_time: float,
    latencies: dict[str, float],
) -> float:
    """
    Track latency for a service call.

    Args:
        service_name: Name of the service
        start_time: Start time of the call
        latencies: Dictionary to store latencies

    Returns:
        Elapsed time in milliseconds
    """
    elapsed_ms = (time.time() - start_time) * 1000
    latencies[service_name] = round(elapsed_ms, 2)
    return elapsed_ms


@router.post("", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest,
    req: Request,
    current_user: ValidateTokenResponse = Depends(get_current_user),
    cache: CacheManager = Depends(get_cache),
) -> QueryResponse:
    """
    Handle user query and orchestrate the service flow.

    Flow:
    1. Validate JWT token (IN-PROCESS via get_current_user dependency)
    2. Call Inference Service for query optimization
    3. Check confidence threshold (0.6)
    4. If confidence < 0.6: return clarification request
    5. If confidence >= 0.6: call Knowledge Service for search
    6. Call Inference Service for generation if needed
    7. Return response to client
    8. Record metrics IN-PROCESS (database + Prometheus)

    Args:
        request: User query request
        req: FastAPI request object
        current_user: Authenticated user from token (in-process validation)
        cache: Redis cache manager

    Returns:
        QueryResponse with answer and metadata
    """
    request_id = str(uuid.uuid4())
    # Set request ID in context for propagation to downstream services
    set_current_request_id(request_id)

    start_time = time.time()
    latencies: dict[str, float] = {}
    branch_taken = "direct"
    escalation_flag = False
    token_usage: Optional[dict[str, int]] = None
    query_confidence = 0.0

    logger.info(
        f"Processing query {request_id}: {request.query[:50]}... "
        f"user={current_user.user_id}, role={current_user.role}"
    )

    try:
        # Step 1: Call Inference Service for query optimization
        optimizer_start = time.time()
        inference_client = service_clients.get_inference_client()

        optimize_response = await inference_client.post(
            "/optimize",
            data={
                "query": request.query,
                "user_role": current_user.role,
            },
        )

        await track_latency("query_optimizer", optimizer_start, latencies)

        if optimize_response is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Query Optimizer service unavailable",
            )

        optimized_queries = optimize_response.get("optimized_queries", [request.query])
        query_confidence = optimize_response.get("confidence", 0.0)

        logger.info(
            f"Query optimized: confidence={query_confidence}, "
            f"queries={optimized_queries}"
        )

        # Step 2: Check confidence threshold
        if query_confidence < settings.confidence_threshold:
            # Return clarification request for low confidence
            branch_taken = "clarification"
            logger.info(
                f"Low confidence ({query_confidence}), requesting clarification"
            )

            # Generate clarification options
            options = []
            for i, opt_query in enumerate(optimized_queries[:3]):
                options.append(
                    {
                        "text": f"Did you mean: {opt_query}?",
                        "query": opt_query,
                    }
                )

            # Add a generic clarification option
            options.append(
                {
                    "text": "Please provide more details about your question.",
                    "query": request.query,
                }
            )

            clarification = ClarificationRequest(
                message="Your query needs more details for accurate answering. Please select an option or provide more information.",
                options=options,
                confidence=query_confidence,
                original_query=request.query,
            )

            # Return clarification as a special response
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "clarification_required",
                    "message": clarification.message,
                    "options": clarification.model_dump()["options"],
                    "confidence": clarification.confidence,
                    "original_query": clarification.original_query,
                },
            )

        # Step 3: Call Knowledge Service for search (check cache first)
        search_start = time.time()
        knowledge_client = service_clients.get_knowledge_client()

        # Try cache first
        cache_key = f"{':'.join(optimized_queries)}:{current_user.role}"
        cached_results = await cache.get_search_cache(cache_key, current_user.role)

        if cached_results:
            logger.info("Using cached search results")
            search_results = cached_results
        else:
            search_response = await knowledge_client.post(
                "/search",
                data={
                    "queries": optimized_queries,
                    "user_role": current_user.role,
                    "top_k": 10,
                },
            )

            await track_latency("search", search_start, latencies)

            if search_response is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Knowledge service unavailable",
                )

            search_results = search_response.get("results", [])

            # Cache the results
            await cache.set_search_cache(
                cache_key,
                current_user.role,
                search_results,
            )

        # Convert to Source objects
        sources = []
        for result in search_results:
            sources.append(
                Source(
                    document_id=result.get("document_id", result.get("id", "")),
                    title=result.get("title"),
                    content=result.get("content", ""),
                    score=result.get("score", 0.0),
                    metadata=result.get("metadata"),
                )
            )

        # Step 4: Call Inference Service for generation if we have results
        if sources:
            generator_start = time.time()

            # Check cache for LLM response (use SHA-256 hash to avoid collisions)
            import hashlib
            source_hashes = [hashlib.sha256(s.content.encode()).hexdigest()[:16] for s in sources[:3]]
            llm_cache_key = f"{request.query}:{':'.join(source_hashes)}"
            cached_llm = await cache.get_llm_response_cache(llm_cache_key)

            if cached_llm:
                answer = cached_llm
                confidence = 0.8  # Assume high confidence for cached responses
                logger.info("Using cached LLM response")
            else:
                generate_response = await inference_client.post(
                    "/generate",
                    data={
                        "query": request.query,
                        "context": [s.model_dump() for s in sources],
                        "user_role": current_user.role,
                    },
                )

                await track_latency("generator", generator_start, latencies)

                if generate_response is None:
                    # Fallback to simple answer if generator fails
                    answer = " ".join([s.content[:200] for s in sources[:2]])
                    confidence = 0.5
                else:
                    answer = generate_response.get("answer", "")
                    confidence = generate_response.get("confidence", 0.5)
                    token_usage = generate_response.get("token_usage")

                    # Cache the LLM response
                    await cache.set_llm_response_cache(llm_cache_key, answer)

            if token_usage:
                escalation_flag = True
                branch_taken = "escalated"

            logger.info(
                f"Generated answer: confidence={confidence}, "
                f"token_usage={token_usage}"
            )
        else:
            # No results found
            answer = "I couldn't find any relevant documents to answer your query. Please try rephrasing your question."
            confidence = 0.0

        # Calculate total latency
        total_latency_ms = (time.time() - start_time) * 1000

        # Step 5: Record metrics IN-PROCESS (no external HTTP call needed)
        try:
            # Update Prometheus metrics directly
            prometheus.update_metrics_on_request(
                user_id=current_user.user_id,
                branch_taken=branch_taken,
                response_time_ms_val=total_latency_ms,
            )
            prometheus.update_query_confidence(
                user_id=current_user.user_id,
                confidence=query_confidence,
            )
            if escalation_flag:
                reason = "low_confidence" if query_confidence < 0.6 else "complex_query"
                prometheus.update_llm_escalation(
                    user_id=current_user.user_id,
                    reason=reason,
                )
            for service, latency_ms in latencies.items():
                prometheus.update_service_latency(
                    service=service,
                    latency_seconds=latency_ms / 1000.0,
                )
            if token_usage:
                for model_type, tokens in token_usage.items():
                    prometheus.update_token_usage(
                        model_type=model_type,
                        tokens=tokens,
                    )

            # Store metric record in database directly (in-process)
            async with AsyncSession(engine) as session:
                await store_metric(
                    session=session,
                    user_id=current_user.user_id,
                    query=request.query,
                    query_confidence=query_confidence,
                    branch_taken=branch_taken,
                    escalation_flag=escalation_flag,
                    latency_per_service=latencies,
                    token_usage=token_usage,
                    response_time_ms=round(total_latency_ms, 2),
                )

                # Store audit log entry directly (in-process)
                await store_audit_log(
                    session=session,
                    user_id=current_user.user_id,
                    action="query_processed",
                    resource_type="query",
                    details={
                        "query": request.query,
                        "query_confidence": query_confidence,
                        "branch_taken": branch_taken,
                        "escalation_flag": escalation_flag,
                        "response_time_ms": round(total_latency_ms, 2),
                    },
                )

        except Exception as e:
            logger.error(f"Failed to record metrics: {e}")

        return QueryResponse(
            answer=answer,
            confidence=confidence,
            sources=sources,
            latency_ms=round(total_latency_ms, 2),
            service_latencies=latencies,
            request_id=request_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing query {request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing query: {str(e)}",
        )


@router.post("/clarification", response_model=QueryResponse)
async def handle_clarification_response(
    request: ClarificationResponse,
    current_user: ValidateTokenResponse = Depends(get_current_user),
    cache: CacheManager = Depends(get_cache),
) -> QueryResponse:
    """
    Handle user's response to a clarification request.

    Args:
        request: User's clarification response
        current_user: Authenticated user from token
        cache: Redis cache manager

    Returns:
        QueryResponse with answer
    """
    # Use the revised query from clarification
    revised_request = QueryRequest(
        query=request.revised_query or "",
        user_id=current_user.user_id,
    )

    # Call handle_query with the revised query
    return await handle_query(revised_request, None, current_user, cache)
