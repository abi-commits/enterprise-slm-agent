"""Generate router for the Inference Service.

This module handles the POST /generate endpoint which generates answers
from context documents using either LLM or simpler methods.

Supports both:
- Standard request/response (POST /generate)
- SSE streaming (POST /generate/stream)
"""

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from core.config.settings import get_settings
from services.inference.generator import llm_client as llm_module
from services.inference.generator import prompts as prompt_utils
from services.inference.schemas import (
    GenerateRequest,
    GenerateResponse,
    StreamChunk,
    StreamingGenerateRequest,
    TokenUsage,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["generate"])

# Get settings
settings = get_settings()


def generate_template_based(
    question: str,
    documents: list[dict[str, Any]],
    user_role: str,
) -> tuple[str, int, float]:
    """Generate answer using template-based method (non-LLM).

    This is a simpler fallback when LLM is not required.

    Args:
        question: User's question
        documents: List of context documents
        user_role: User's role for context

    Returns:
        Tuple of (answer, tokens_used, cost_usd)
    """
    if not documents:
        return (
            "I don't have enough context to answer your question. "
            "Please try a more specific query or ensure documents are available.",
            0,
            0.0,
        )

    # Simple template-based generation
    # Extract relevant sentences from documents based on question keywords
    question_lower = question.lower()
    question_words = set(question_lower.split())

    best_content = ""
    best_score = 0.0

    for doc in documents:
        content = doc.get("content", "")
        score = doc.get("score", 0.5)

        # Simple keyword matching
        content_lower = content.lower()
        matches = sum(1 for word in question_words if word in content_lower)

        if matches > best_score:
            best_score = matches
            best_content = content

    if best_content:
        # Create a simple answer by extracting relevant content
        answer = f"Based on the available documents:\n\n{best_content[:500]}"

        # Estimate tokens (rough approximation: 1 token ~ 4 characters)
        tokens_used = len(answer) // 4
        cost = 0.0  # No cost for template-based generation

        return answer, tokens_used, cost

    return (
        "I found some relevant documents but couldn't extract a specific answer. "
        "Please check the documents directly or try rephrasing your question.",
        0,
        0.0,
    )


@router.post("/generate", response_model=GenerateResponse)
async def generate_answer(request: GenerateRequest) -> GenerateResponse:
    """Generate an answer from context documents.

    This endpoint is called when:
    - Query optimizer confidence is low (< 0.6)
    - Reranker indicates high ambiguity
    - Context complexity exceeds threshold
    - User explicitly requests LLM generation

    Args:
        request: GenerateRequest with query and context documents

    Returns:
        GenerateResponse with generated answer and metadata
    """
    start_time = time.time()

    logger.info(
        f"Generating answer for query: '{request.query[:100]}...', "
        f"use_llm={request.use_llm}, documents={len(request.context_documents)}"
    )

    # Determine generation method
    if request.use_llm:
        # Use LLM for generation
        try:
            # Build prompt
            prompt = prompt_utils.build_generation_prompt(
                question=request.query,
                documents=request.context_documents,
                user_role=request.user_role,
                include_few_shot=False,  # Can be enabled for better results
            )

            # Get LLM client
            llm = llm_module.get_llm_client()

            # Generate response
            llm_response = await llm.generate(
                prompt=prompt,
                model=settings.llm_model,
                max_tokens=1024,
                temperature=0.7,
                top_p=0.9,
            )

            # Extract answer
            answer = prompt_utils.extract_answer_from_response(llm_response.text)

            # If LLM didn't return anything, fall back to template
            if not answer or "[LLM generation not available" in answer:
                logger.warning(
                    "LLM generation failed or not available, falling back to template"
                )
                answer, tokens, cost = generate_template_based(
                    request.query,
                    request.context_documents,
                    request.user_role,
                )
                total_tokens = tokens
                cost_usd = cost
                model_used = "template"
            else:
                answer = llm_response.text
                total_tokens = llm_response.total_tokens
                cost_usd = llm_response.cost_usd
                model_used = llm_response.model

            token_usage = TokenUsage(
                prompt_tokens=llm_response.prompt_tokens,
                completion_tokens=llm_response.completion_tokens,
                total_tokens=total_tokens,
            )

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Fall back to template-based generation
            answer, tokens, cost = generate_template_based(
                request.query,
                request.context_documents,
                request.user_role,
            )
            total_tokens = tokens
            cost_usd = cost
            model_used = "template"
            token_usage = TokenUsage(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            )
    else:
        # Use simpler template-based generation
        answer, total_tokens, cost_usd = generate_template_based(
            request.query,
            request.context_documents,
            request.user_role,
        )
        model_used = "template"
        token_usage = TokenUsage(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=total_tokens,
        )

    # Calculate processing time
    processing_time_ms = (time.time() - start_time) * 1000

    logger.info(
        f"Generation completed: model={model_used}, "
        f"tokens={total_tokens}, cost=${cost_usd:.6f}, time={processing_time_ms:.2f}ms"
    )

    return GenerateResponse(
        answer=answer,
        tokens_used=total_tokens,
        cost_usd=cost_usd,
        model_used=model_used,
        processing_time_ms=processing_time_ms,
        token_usage=token_usage,
    )


@router.post("/generate/stream")
async def generate_answer_stream(request: StreamingGenerateRequest) -> StreamingResponse:
    """Generate an answer with streaming response using Server-Sent Events.

    Tokens are streamed as they're generated, providing better UX for
    long responses. The client should handle SSE format:
    
    ```
    data: {"token": "Hello", "is_final": false}
    data: {"token": " world", "is_final": false}
    data: {"token": "", "is_final": true, "finish_reason": "stop"}
    ```

    Args:
        request: StreamingGenerateRequest with query and context

    Returns:
        StreamingResponse with SSE content type
    """
    logger.info(
        f"Starting streaming generation for query: '{request.query[:100]}...', "
        f"documents={len(request.context_documents)}"
    )
    
    async def generate_sse():
        """Generator that yields SSE-formatted chunks."""
        try:
            # Build prompt
            prompt = prompt_utils.build_generation_prompt(
                question=request.query,
                documents=request.context_documents,
                user_role=request.user_role,
                include_few_shot=False,
            )
            
            # Get LLM client
            llm = llm_module.get_llm_client()
            
            # Stream tokens
            async for chunk in llm.generate_stream(
                prompt=prompt,
                model=settings.llm_model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            ):
                # Format as SSE
                yield f"data: {chunk.to_sse_data()}\n\n"
                
                if chunk.is_final:
                    break
                    
        except Exception as e:
            logger.error(f"Streaming generation error: {e}")
            error_chunk = StreamChunk(
                token=f"[Error: {str(e)}]",
                is_final=True,
                finish_reason="error",
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
    
    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
