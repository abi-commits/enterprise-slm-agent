"""Search router for the Context Engine Service."""

import logging
import time
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from services.context_engine import schemas as knowledge_schemas
from services.context_engine.context_optimizer import ContextOptimizer
from services.context_engine.retrieval import embeddings as embedding_service
from services.context_engine.retrieval import reranker as reranker_service
from services.context_engine.retrieval import vector_store as qdrant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@lru_cache()
def get_context_optimizer() -> ContextOptimizer:
    """Singleton ContextOptimizer dependency."""
    return ContextOptimizer()


def _deduplicate_raw_results(
    raw_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate Qdrant results by point ID, keeping highest score."""
    seen: dict[str, dict[str, Any]] = {}
    for result in raw_results:
        point_id = str(result["id"])
        score = result.get("score", 0.0)
        if point_id not in seen or score > seen[point_id].get("score", 0):
            seen[point_id] = result
    return list(seen.values())


@router.post("", response_model=knowledge_schemas.SearchResponse)
async def search_documents(request: knowledge_schemas.SearchRequest) -> knowledge_schemas.SearchResponse:
    """Search documents with vector search and reranking, supporting single or multiple queries.

    This endpoint:
    1. For each query (if `queries` provided) or single `query`:
       - Generates embeddings using BAAI/bge-small-en-v1.5
       - Searches Qdrant with RBAC filtering
    2. Combines results from all queries, deduplicates
    3. Re-ranks using cross-encoder/ms-marco-MiniLM-L-6-v2
    4. Optionally applies context engineering to produce formatted context
    5. Returns top-K results (and engineered_context if requested)

    Args:
        request: Search request with either `query` or `queries`, plus user_role, top_k,
                 context_engineering options, etc.

    Returns:
        SearchResponse with ranked documents, optional engineered context, and metrics.
    """
    start_time = time.time()

    try:
        # Determine which queries to process
        try:
            queries = request.get_queries()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either 'query' or 'queries' must be provided",
            )

        logger.info(f"Processing {len(queries)} query(ies) for role {request.user_role}")
        retrieval_limit = max(request.top_k * 3, 20)

        # Step 1: For each query, generate embedding and retrieve from Qdrant
        all_raw_results: list[dict[str, Any]] = []
        for q in queries:
            q_embedding = embedding_service.generate_query_embedding(q)
            raw = qdrant_service.search_documents(
                query_embedding=q_embedding,
                user_role=request.user_role,
                top_k=retrieval_limit,
                additional_filters=request.filters,
            )
            all_raw_results.extend(raw)

        if not all_raw_results:
            logger.info("No documents found for any query")
            return knowledge_schemas.SearchResponse(
                results=[],
                total=0,
                processing_time_ms=(time.time() - start_time) * 1000,
                engineered_context=None,
                context_metrics=None,
            )

        # Step 2: Deduplicate by document ID (keep highest score)
        unique_raw = _deduplicate_raw_results(all_raw_results)
        logger.info(f"Combined {len(all_raw_results)} results, {len(unique_raw)} unique")

        # Step 3: Build document list for reranking
        documents = []
        for result in unique_raw:
            payload = result.get("payload", {})
            content = payload.get("content", "")
            if content:
                documents.append({
                    "id": str(result["id"]),
                    "content": content,
                    "score": result.get("score", 0.0),  # vector similarity score
                    "metadata": {k: v for k, v in payload.items() if k != "content"},
                    "source": payload.get("source", "unknown"),
                })

        if not documents:
            logger.info("No document content extracted")
            return knowledge_schemas.SearchResponse(
                results=[],
                total=len(unique_raw),
                processing_time_ms=(time.time() - start_time) * 1000,
                engineered_context=None,
                context_metrics=None,
            )

        # Step 4: Re-rank with Cross-Encoder using the original query if available, else first query
        rerank_query = request.query or queries[0]
        logger.info(f"Re-ranking {len(documents)} documents with query: {rerank_query[:50]}...")
        doc_contents = [doc["content"] for doc in documents]
        reranked_indices = reranker_service.rerank_documents(
            query=rerank_query,
            documents=doc_contents,
            top_k=request.top_k,
        )

        # Step 5: Build response documents with rerank scores
        results = []
        for idx, rerank_score in reranked_indices:
            doc = documents[idx]
            results.append(knowledge_schemas.Document(
                id=doc["id"],
                content=doc["content"],
                score=float(rerank_score),
                metadata=doc["metadata"],
                source=doc["source"],
            ))

        processing_time_ms = (time.time() - start_time) * 1000
        logger.info(f"Search completed: {len(results)} results in {processing_time_ms:.2f}ms")

        # Step 6: Optional context engineering
        engineered_context = None
        context_metrics_obj = None
        if request.context_engineering and results:
            try:
                optimizer = get_context_optimizer()
                config = request.context_config or knowledge_schemas.ContextConfig()

                # Convert results to dicts
                doc_dicts = [
                    {
                        "id": doc.id,
                        "content": doc.content,
                        "score": doc.score,
                        "metadata": doc.metadata,
                        "source": doc.source,
                    }
                    for doc in results
                ]

                optimized = optimizer.optimize(
                    documents=doc_dicts,
                    query=request.query or queries[0],
                    keywords=request.keywords,
                    user_role=request.user_role,
                    conversation_history=request.conversation_history,
                )

                engineered_context = optimized.formatted_context
                context_metrics_obj = knowledge_schemas.ContextMetrics(
                    documents_included=optimized.documents_included,
                    documents_original=optimized.documents_original,
                    tokens_used=optimized.tokens_used,
                    budget_remaining=optimized.budget_remaining,
                    coverage_score=optimized.coverage_score,
                    truncated_count=optimized.metadata.get("truncated_count", 0),
                    deduplication_removed=optimized.metadata.get("deduplication_removed", 0),
                )
                logger.info(
                    f"Context engineering: {optimized.tokens_used} tokens, "
                    f"coverage={optimized.coverage_score:.2f}"
                )
            except Exception as e:
                logger.exception(f"Context engineering error: {e}")
                engineered_context = None
                context_metrics_obj = None

        # Return final response
        return knowledge_schemas.SearchResponse(
            results=results,
            total=len(unique_raw),
            processing_time_ms=processing_time_ms,
            engineered_context=engineered_context,
            context_metrics=context_metrics_obj,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        ) from e