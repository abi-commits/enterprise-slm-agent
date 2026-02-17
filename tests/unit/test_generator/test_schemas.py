"""Tests for Generator Service schemas."""

import pytest
from pydantic import ValidationError

from services.inference.schemas import (
    GenerateRequest,
    TokenUsage,
    GenerateResponse,
    HealthResponse,
    GenerationMethod,
    EscalationReason,
)


class TestGenerateRequest:
    """Test cases for GenerateRequest model."""

    def test_generate_request_valid(self):
        """Test GenerateRequest with valid data."""
        request = GenerateRequest(
            query="What is the vacation policy?",
            context_documents=[
                {
                    "id": "doc-1",
                    "content": "The vacation policy allows 15 days...",
                    "score": 0.95,
                    "source": "HR Handbook",
                }
            ],
            user_role="HR",
            use_llm=True,
        )
        
        assert request.query == "What is the vacation policy?"
        assert len(request.context_documents) == 1
        assert request.user_role == "HR"

    def test_generate_request_defaults(self):
        """Test GenerateRequest with default values."""
        request = GenerateRequest(
            query="What is the vacation policy?",
            user_role="HR",
        )
        
        assert request.use_llm is True
        assert request.context_documents == []
        assert request.conversation_history is None

    def test_generate_request_empty_query(self):
        """Test GenerateRequest with empty query."""
        with pytest.raises(ValidationError):
            GenerateRequest(
                query="",
                user_role="HR",
            )

    def test_generate_request_query_too_long(self):
        """Test GenerateRequest with query too long."""
        with pytest.raises(ValidationError):
            GenerateRequest(
                query="a" * 1001,
                user_role="HR",
            )

    def test_generate_request_with_conversation_history(self):
        """Test GenerateRequest with conversation history."""
        history = [
            {"role": "user", "content": "What is the vacation policy?"},
            {"role": "assistant", "content": "The vacation policy allows 15 days."},
        ]
        
        request = GenerateRequest(
            query="Can I carry over unused days?",
            user_role="HR",
            conversation_history=history,
        )
        
        assert len(request.conversation_history) == 2


class TestTokenUsage:
    """Test cases for TokenUsage model."""

    def test_token_usage_defaults(self):
        """Test TokenUsage with default values."""
        usage = TokenUsage()
        
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_token_usage_custom(self):
        """Test TokenUsage with custom values."""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_token_usage_auto_total(self):
        """Test TokenUsage defaults total_tokens to 0 when not provided."""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
        )

        assert usage.total_tokens == 0


class TestGenerateResponse:
    """Test cases for GenerateResponse model."""

    def test_generate_response_valid(self):
        """Test GenerateResponse with valid data."""
        response = GenerateResponse(
            answer="The vacation policy allows 15 days per year.",
            tokens_used=150,
            cost_usd=0.001,
            model_used="Qwen/Qwen2.5-1.5B-Instruct",
            processing_time_ms=500.0,
            token_usage=TokenUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        )
        
        assert response.answer == "The vacation policy allows 15 days per year."
        assert response.tokens_used == 150
        assert response.cost_usd == 0.001


class TestHealthResponse:
    """Test cases for HealthResponse model."""

    def test_health_response_valid(self):
        """Test HealthResponse with valid data."""
        response = HealthResponse(
            status="healthy",
            vllm_connected=True,
            model_loaded=True,
            vllm_available=True,
        )

        assert response.status == "healthy"
        assert response.vllm_connected is True
        assert response.model_loaded is True
        assert response.vllm_available is True


class TestGenerationMethod:
    """Test cases for GenerationMethod."""

    def test_generation_method_values(self):
        """Test GenerationMethod enum values."""
        assert GenerationMethod.LLM == "llm"
        assert GenerationMethod.TEMPLATE == "template"
        assert GenerationMethod.SLM == "slm"


class TestEscalationReason:
    """Test cases for EscalationReason."""

    def test_escalation_reason_values(self):
        """Test EscalationReason enum values."""
        assert EscalationReason.LOW_CONFIDENCE == "low_confidence"
        assert EscalationReason.HIGH_RERANKER_AMBIGUITY == "high_reranker_ambiguity"
        assert EscalationReason.HIGH_CONTEXT_COMPLEXITY == "high_context_complexity"
        assert EscalationReason.EXPLICIT_REQUEST == "explicit_request"
        assert EscalationReason.COMPLEX_REASONING == "complex_reasoning"
