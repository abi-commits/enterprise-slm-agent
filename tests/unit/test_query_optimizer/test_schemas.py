"""Tests for Query Optimizer Service schemas."""

import pytest
from pydantic import ValidationError

from services.inference.schemas import (
    OptimizeRequest,
    OptimizeResponse,
    HealthResponse,
    ErrorResponse,
)


class TestOptimizeRequest:
    """Test cases for OptimizeRequest model."""

    def test_optimize_request_valid(self):
        """Test OptimizeRequest with valid data."""
        request = OptimizeRequest(
            query="What is the vacation policy?",
            user_context="User is in HR department",
        )
        
        assert request.query == "What is the vacation policy?"
        assert request.user_context == "User is in HR department"

    def test_optimize_request_without_context(self):
        """Test OptimizeRequest without optional user_context."""
        request = OptimizeRequest(
            query="What is the vacation policy?",
        )
        
        assert request.user_context is None

    def test_optimize_request_empty_query(self):
        """Test OptimizeRequest with empty query."""
        with pytest.raises(ValidationError):
            OptimizeRequest(query="")

    def test_optimize_request_query_too_long(self):
        """Test OptimizeRequest with query too long."""
        with pytest.raises(ValidationError):
            OptimizeRequest(query="a" * 1001)


class TestOptimizeResponse:
    """Test cases for OptimizeResponse model."""

    def test_optimize_response_valid(self):
        """Test OptimizeResponse with valid data."""
        response = OptimizeResponse(
            optimized_queries=[
                "company vacation policy guidelines 2024",
                "employee paid time off PTO policy",
                "vacation leave entitlements and accrual rules",
            ],
            confidence=0.85,
            keywords=["vacation", "PTO", "paid time off", "leave", "policy"],
            processing_time_ms=125.5,
        )
        
        assert len(response.optimized_queries) == 3
        assert response.confidence == 0.85
        assert len(response.keywords) == 5

    def test_optimize_response_minimal(self):
        """Test OptimizeResponse with minimal data."""
        response = OptimizeResponse(
            optimized_queries=["vacation policy"],
            confidence=0.5,
            keywords=["vacation"],
            processing_time_ms=100.0,
        )
        
        assert len(response.optimized_queries) == 1

    def test_optimize_response_confidence_out_of_range(self):
        """Test OptimizeResponse with confidence out of range."""
        with pytest.raises(ValidationError):
            OptimizeResponse(
                optimized_queries=["vacation policy"],
                confidence=1.5,  # Should be <= 1.0
                keywords=["vacation"],
                processing_time_ms=100.0,
            )

    def test_optimize_response_confidence_negative(self):
        """Test OptimizeResponse with negative confidence."""
        with pytest.raises(ValidationError):
            OptimizeResponse(
                optimized_queries=["vacation policy"],
                confidence=-0.1,  # Should be >= 0.0
                keywords=["vacation"],
                processing_time_ms=100.0,
            )


class TestHealthResponse:
    """Test cases for HealthResponse model."""

    def test_health_response_valid(self):
        """Test HealthResponse with valid data."""
        response = HealthResponse(
            status="healthy",
            vllm_connected=True,
            model_loaded=True,
            model_name="Qwen/Qwen2.5-1.5B-Instruct",
            vllm_available=True,
        )

        assert response.status == "healthy"
        assert response.vllm_connected is True
        assert response.model_loaded is True
        assert response.vllm_available is True

    def test_health_response_minimal(self):
        """Test HealthResponse with minimal data."""
        response = HealthResponse(
            status="healthy",
            vllm_connected=False,
            model_loaded=True,
            vllm_available=False,
        )

        assert response.model_name is None


class TestErrorResponse:
    """Test cases for ErrorResponse model."""

    def test_error_response_valid(self):
        """Test ErrorResponse with valid data."""
        response = ErrorResponse(
            error="MODEL_NOT_FOUND",
            message="The requested model could not be loaded",
        )
        
        assert response.error == "MODEL_NOT_FOUND"
        assert response.message == "The requested model could not be loaded"

    def test_error_response_with_detail(self):
        """Test ErrorResponse with detail."""
        response = ErrorResponse(
            error="VALIDATION_ERROR",
            message="Invalid request",
            detail="Query parameter is required",
        )
        
        assert response.detail == "Query parameter is required"

    def test_error_response_minimal(self):
        """Test ErrorResponse with minimal data."""
        response = ErrorResponse(
            error="UNKNOWN_ERROR",
            message="An unknown error occurred",
        )
        
        assert response.detail is None
