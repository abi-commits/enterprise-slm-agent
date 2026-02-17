"""Search router for the Knowledge Service."""

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, status

from services.knowledge.retrieval import embeddings as embedding_service
from services.knowledge.retrieval import reranker as reranker_service
from services.knowledge import schemas as knowledge_schemas
from services.knowledge.retrieval import vector_store as qdrant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=knowledge_schemas.SearchResponse)
async def search_documents(request: knowledge_schemas.SearchRequest) -> knowledge_schemas.SearchResponse:
    """Search documents with vector search and reranking.

    This endpoint:
    1. Generates embeddings for the query using BAAI/bge-small-en-v1.5
    2. Searches Qdrant vector database with role-based filtering
    3. Re-ranks results using cross-encoder/ms-marco-MiniLM-L-6-v2
    4. Returns top-K results with scores

    Args:
        request: Search request with query, user_role, top_k, and optional filters.

    Returns:
        SearchResponse with ranked documents and metadata.
    """
    start_time = time.time()

    try:
        # Step 1: Generate query embedding
        logger.info(f"Generating embedding for query: {request.query[:50]}...")
        query_embedding = embedding_service.generate_query_embedding(request.query)

        # Step 2: Search Qdrant with RBAC filtering
        # Retrieve more results than requested to allow for reranking
        retrieval_limit = max(request.top_k * 3, 20)
        logger.info(f"Searching Qdrant with role: {request.user_role}, limit: {retrieval_limit}")

        raw_results = qdrant_service.search_documents(
            query_embedding=query_embedding,
            user_role=request.user_role,
            top_k=retrieval_limit,
            additional_filters=request.filters,
        )

        if not raw_results:
            logger.info("No documents found matching the query")
            return knowledge_schemas.SearchResponse(
                results=[],
                total=0,
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        # Step 3: Extract documents for reranking
        documents = []
        for result in raw_results:
            payload = result.get("payload", {})
            content = payload.get("content", "")
            if content:
                documents.append({
                    "id": str(result["id"]),
                    "content": content,
                    "score": result.get("score", 0.0),
                    "metadata": {k: v for k, v in payload.items() if k != "content"},
                    "source": payload.get("source", "unknown"),
                })

        if not documents:
            logger.info("No document content found in results")
            return knowledge_schemas.SearchResponse(
                results=[],
                total=0,
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        # Step 4: Re-rank documents using Cross-Encoder
        logger.info(f"Re-ranking {len(documents)} documents")
        doc_contents = [doc["content"] for doc in documents]
        reranked_indices = reranker_service.rerank_documents(
            query=request.query,
            documents=doc_contents,
            top_k=request.top_k,
        )

        # Step 5: Build final response with reranked scores
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

        return knowledge_schemas.SearchResponse(
            results=results,
            total=len(raw_results),
            processing_time_ms=processing_time_ms,
        )

    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )
