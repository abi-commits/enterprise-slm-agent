"""Tests for API Gateway schemas (consolidated from gateway service).

These tests cover schemas that were originally in services.gateway.schemas
and are now split across services.api.schemas, services.inference.schemas,
and services.knowledge.schemas.
"""

import pytest
from pydantic import ValidationError

from services.api.schemas import (
    QueryRequest,
    Source,
    QueryResponse,
    ClarificationOption,
    ClarificationRequest,
    ClarificationResponse,
    MetricRequest,
    ValidateTokenRequest,
    ValidateTokenResponse,
)
from services.inference.schemas import (
    OptimizeRequest,
    OptimizeResponse,
    GenerateRequest,
    GenerateResponse,
)
from services.knowledge.schemas import (
    SearchRequest,
    SearchResponse,
)


class TestQueryRequest:
    """Test cases for QueryRequest model."""

    def test_query_request_valid(self):
        """Test QueryRequest with valid data."""
        request = QueryRequest(
            query="What is the vacation policy?",
            user_id="12345678-1234-1234-1234-123456789012",
            session_id="session-123",
        )

        assert request.query == "What is the vacation policy?"
        assert request.user_id == "12345678-1234-1234-1234-123456789012"
        assert request.session_id == "session-123"

    def test_query_request_without_session(self):
        """Test QueryRequest without optional session_id."""
        request = QueryRequest(
            query="What is the vacation policy?",
            user_id="12345678-1234-1234-1234-123456789012",
        )

        assert request.session_id is None

    def test_query_request_empty_query(self):
        """Test QueryRequest with empty query."""
        with pytest.raises(ValidationError):
            QueryRequest(
                query="",
                user_id="12345678-1234-1234-1234-123456789012",
            )

    def test_query_request_query_too_long(self):
        """Test QueryRequest with query too long."""
        with pytest.raises(ValidationError):
            QueryRequest(
                query="a" * 1001,
                user_id="12345678-1234-1234-1234-123456789012",
            )


class TestSource:
    """Test cases for Source model."""

    def test_source_valid(self):
        """Test Source with valid data."""
        source = Source(
            document_id="doc-123",
            title="HR Policy",
            content="The vacation policy allows 15 days...",
            score=0.95,
            metadata={"author": "HR"},
        )

        assert source.document_id == "doc-123"
        assert source.score == 0.95

    def test_source_minimal(self):
        """Test Source with minimal data."""
        source = Source(
            document_id="doc-123",
            content="Content here",
            score=0.5,
        )

        assert source.title is None
        assert source.metadata is None


class TestQueryResponse:
    """Test cases for QueryResponse model."""

    def test_query_response_valid(self):
        """Test QueryResponse with valid data."""
        response = QueryResponse(
            answer="The vacation policy allows 15 days.",
            confidence=0.9,
            sources=[],
            latency_ms=250.5,
        )

        assert response.answer == "The vacation policy allows 15 days."
        assert response.confidence == 0.9
        assert response.latency_ms == 250.5


class TestClarificationOption:
    """Test cases for ClarificationOption model."""

    def test_clarification_option_valid(self):
        """Test ClarificationOption with valid data."""
        option = ClarificationOption(
            text="Are you asking about vacation or sick leave?",
            query="sick leave policy",
        )

        assert option.text == "Are you asking about vacation or sick leave?"
        assert option.query == "sick leave policy"


class TestClarificationRequest:
    """Test cases for ClarificationRequest model."""

    def test_clarification_request_valid(self):
        """Test ClarificationRequest with valid data."""
        request = ClarificationRequest(
            message="Could you clarify?",
            options=[
                ClarificationOption(text="Option 1", query="query1"),
                ClarificationOption(text="Option 2", query="query2"),
            ],
            confidence=0.5,
            original_query="policy",
        )

        assert len(request.options) == 2
        assert request.confidence == 0.5


class TestOptimizeRequest:
    """Test cases for OptimizeRequest model."""

    def test_optimize_request_valid(self):
        """Test OptimizeRequest with valid data."""
        request = OptimizeRequest(
            query="vacation policy",
            user_context="User is in HR department",
        )

        assert request.query == "vacation policy"
        assert request.user_context == "User is in HR department"


class TestOptimizeResponse:
    """Test cases for OptimizeResponse model."""

    def test_optimize_response_valid(self):
        """Test OptimizeResponse with valid data."""
        response = OptimizeResponse(
            optimized_queries=[
                "company vacation policy",
                "employee PTO rules",
            ],
            confidence=0.85,
            keywords=["vacation", "PTO"],
            processing_time_ms=100.0,
        )

        assert len(response.optimized_queries) == 2
        assert response.confidence == 0.85


class TestSearchRequest:
    """Test cases for SearchRequest model."""

    def test_search_request_valid(self):
        """Test SearchRequest with valid data."""
        request = SearchRequest(
            query="vacation policy",
            user_role="HR",
            top_k=10,
        )

        assert request.query == "vacation policy"
        assert request.top_k == 10

    def test_search_request_defaults(self):
        """Test SearchRequest with default values."""
        request = SearchRequest(
            query="vacation policy",
            user_role="HR",
        )

        assert request.top_k == 10


class TestGenerateRequest:
    """Test cases for GenerateRequest model."""

    def test_generate_request_valid(self):
        """Test GenerateRequest with valid data."""
        request = GenerateRequest(
            query="What is the vacation policy?",
            context_documents=[
                {
                    "document_id": "doc-1",
                    "title": "HR Policy",
                    "content": "The vacation policy allows 15 days...",
                    "score": 0.95,
                }
            ],
            user_role="HR",
        )

        assert request.query == "What is the vacation policy?"
        assert len(request.context_documents) == 1

    def test_generate_request_empty_context(self):
        """Test GenerateRequest with empty context."""
        request = GenerateRequest(
            query="What is the vacation policy?",
            context_documents=[],
            user_role="HR",
        )

        assert len(request.context_documents) == 0


class TestMetricRequest:
    """Test cases for MetricRequest model."""

    def test_metric_request_valid(self):
        """Test MetricRequest with valid data."""
        request = MetricRequest(
            user_id="12345678-1234-1234-1234-123456789012",
            query="vacation policy",
            query_confidence=0.85,
            branch_taken="direct",
            escalation_flag=False,
            latency_per_service={
                "optimizer": 50.0,
                "search": 100.0,
                "generator": 200.0,
            },
            response_time_ms=350.0,
        )

        assert request.user_id == "12345678-1234-1234-1234-123456789012"
        assert request.query_confidence == 0.85
        assert request.branch_taken == "direct"


class TestValidateTokenRequest:
    """Test cases for ValidateTokenRequest model."""

    def test_validate_token_request_valid(self):
        """Test ValidateTokenRequest with valid data."""
        request = ValidateTokenRequest(
            token="test-token",
        )

        assert request.token == "test-token"


class TestValidateTokenResponse:
    """Test cases for ValidateTokenResponse model."""

    def test_validate_token_response_valid_token(self):
        """Test ValidateTokenResponse with valid token."""
        response = ValidateTokenResponse(
            valid=True,
            user_id="12345678-1234-1234-1234-123456789012",
            username="testuser",
            role="Admin",
        )

        assert response.valid is True
        assert response.user_id == "12345678-1234-1234-1234-123456789012"

    def test_validate_token_response_invalid_token(self):
        """Test ValidateTokenResponse with invalid token."""
        response = ValidateTokenResponse(
            valid=False,
        )

        assert response.valid is False
        assert response.user_id is None
