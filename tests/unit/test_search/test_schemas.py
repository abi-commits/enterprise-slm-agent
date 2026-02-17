"""Tests for Search Service schemas."""

import pytest
from pydantic import ValidationError

from services.knowledge.schemas import (
    SearchRequest,
    Document,
    SearchResponse,
    HealthResponse,
)


class TestSearchRequest:
    """Test cases for SearchRequest model."""

    def test_search_request_valid(self):
        """Test SearchRequest with valid data."""
        request = SearchRequest(
            query="vacation policy",
            user_role="HR",
            top_k=10,
            filters={"department": "HR"},
        )
        
        assert request.query == "vacation policy"
        assert request.user_role == "HR"
        assert request.top_k == 10

    def test_search_request_defaults(self):
        """Test SearchRequest with default values."""
        request = SearchRequest(
            query="vacation policy",
            user_role="HR",
        )
        
        assert request.top_k == 10
        assert request.filters is None

    def test_search_request_empty_query(self):
        """Test SearchRequest with empty query."""
        with pytest.raises(ValidationError):
            SearchRequest(
                query="",
                user_role="HR",
            )

    def test_search_request_query_too_long(self):
        """Test SearchRequest with query too long."""
        with pytest.raises(ValidationError):
            SearchRequest(
                query="a" * 1001,
                user_role="HR",
            )

    def test_search_request_invalid_top_k(self):
        """Test SearchRequest with invalid top_k."""
        with pytest.raises(ValidationError):
            SearchRequest(
                query="vacation policy",
                user_role="HR",
                top_k=0,
            )


class TestDocument:
    """Test cases for Document model."""

    def test_document_valid(self):
        """Test Document with valid data."""
        doc = Document(
            id="doc-123",
            content="The vacation policy allows 15 days...",
            score=0.95,
            metadata={"author": "HR"},
            source="HR Handbook",
        )
        
        assert doc.id == "doc-123"
        assert doc.score == 0.95
        assert doc.source == "HR Handbook"

    def test_document_minimal(self):
        """Test Document with minimal data."""
        doc = Document(
            id="doc-123",
            content="Content here",
            score=0.5,
            source="Test",
        )
        
        assert doc.metadata == {}

    def test_document_score_range(self):
        """Test Document score is within valid range."""
        doc = Document(
            id="doc-123",
            content="Content",
            score=1.0,
            source="Test",
        )
        
        assert doc.score <= 1.0
        assert doc.score >= 0.0


class TestSearchResponse:
    """Test cases for SearchResponse model."""

    def test_search_response_valid(self):
        """Test SearchResponse with valid data."""
        docs = [
            Document(id="doc-1", content="Content 1", score=0.9, source="Source 1"),
            Document(id="doc-2", content="Content 2", score=0.8, source="Source 2"),
        ]
        
        response = SearchResponse(
            results=docs,
            total=2,
            processing_time_ms=150.5,
        )
        
        assert len(response.results) == 2
        assert response.total == 2
        assert response.processing_time_ms == 150.5

    def test_search_response_empty(self):
        """Test SearchResponse with empty results."""
        response = SearchResponse(
            results=[],
            total=0,
            processing_time_ms=50.0,
        )
        
        assert len(response.results) == 0
        assert response.total == 0


class TestHealthResponse:
    """Test cases for HealthResponse model."""

    def test_health_response_valid(self):
        """Test HealthResponse with valid data."""
        response = HealthResponse(
            status="healthy",
            qdrant_connected=True,
            embedding_model_loaded=True,
            reranker_model_loaded=True,
        )
        
        assert response.status == "healthy"
        assert response.qdrant_connected is True

    def test_health_response_partial(self):
        """Test HealthResponse with partial services."""
        response = HealthResponse(
            status="degraded",
            qdrant_connected=False,
            embedding_model_loaded=True,
            reranker_model_loaded=False,
        )
        
        assert response.status == "degraded"
