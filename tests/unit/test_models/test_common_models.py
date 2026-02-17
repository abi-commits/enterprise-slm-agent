"""Tests for common models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from core.models.common import (
    HealthCheck,
    ErrorResponse,
    BaseResponse,
    PaginationParams,
    PaginatedResponse,
)


class TestHealthCheck:
    """Test cases for HealthCheck model."""

    def test_health_check_valid(self):
        """Test HealthCheck with valid data."""
        health = HealthCheck(
            status="healthy",
            service="gateway",
        )
        
        assert health.status == "healthy"
        assert health.service == "gateway"
        assert health.timestamp is not None

    def test_health_check_with_timestamp(self):
        """Test HealthCheck with custom timestamp."""
        now = datetime.utcnow()
        health = HealthCheck(
            status="healthy",
            service="gateway",
            timestamp=now,
        )
        
        assert health.timestamp == now


class TestErrorResponse:
    """Test cases for ErrorResponse model."""

    def test_error_response_valid(self):
        """Test ErrorResponse with valid data."""
        error = ErrorResponse(
            error="NOT_FOUND",
            message="Resource not found",
        )
        
        assert error.error == "NOT_FOUND"
        assert error.message == "Resource not found"
        assert error.request_id is None
        assert error.timestamp is not None

    def test_error_response_with_request_id(self):
        """Test ErrorResponse with request ID."""
        error = ErrorResponse(
            error="NOT_FOUND",
            message="Resource not found",
            request_id="req-123",
        )
        
        assert error.request_id == "req-123"


class TestBaseResponse:
    """Test cases for BaseResponse generic model."""

    def test_base_response_success(self):
        """Test BaseResponse with success."""
        response = BaseResponse(
            success=True,
            data={"key": "value"},
        )
        
        assert response.success is True
        assert response.data == {"key": "value"}
        assert response.message is None

    def test_base_response_with_message(self):
        """Test BaseResponse with message."""
        response = BaseResponse(
            success=True,
            data={"key": "value"},
            message="Operation completed",
        )
        
        assert response.message == "Operation completed"

    def test_base_response_with_null_data(self):
        """Test BaseResponse with null data."""
        response = BaseResponse(
            success=False,
            data=None,
            message="Operation failed",
        )
        
        assert response.data is None


class TestPaginationParams:
    """Test cases for PaginationParams model."""

    def test_pagination_defaults(self):
        """Test PaginationParams with default values."""
        params = PaginationParams()
        
        assert params.page == 1
        assert params.page_size == 20

    def test_pagination_custom(self):
        """Test PaginationParams with custom values."""
        params = PaginationParams(
            page=2,
            page_size=50,
        )
        
        assert params.page == 2
        assert params.page_size == 50

    def test_pagination_page_invalid(self):
        """Test PaginationParams with invalid page."""
        with pytest.raises(ValidationError):
            PaginationParams(page=0)

    def test_pagination_page_size_invalid(self):
        """Test PaginationParams with invalid page_size."""
        with pytest.raises(ValidationError):
            PaginationParams(page_size=101)


class TestPaginatedResponse:
    """Test cases for PaginatedResponse model."""

    def test_paginated_response_valid(self):
        """Test PaginatedResponse with valid data."""
        items = ["item1", "item2", "item3"]
        response = PaginatedResponse(
            items=items,
            total=100,
            page=1,
            page_size=20,
            total_pages=5,
        )
        
        assert response.items == items
        assert response.total == 100
        assert response.page == 1
        assert response.page_size == 20
        assert response.total_pages == 5

    def test_paginated_response_empty(self):
        """Test PaginatedResponse with empty items."""
        response = PaginatedResponse(
            items=[],
            total=0,
            page=1,
            page_size=20,
            total_pages=0,
        )
        
        assert len(response.items) == 0
        assert response.total == 0

    def test_paginated_response_with_dict_items(self):
        """Test PaginatedResponse with dictionary items."""
        items = [
            {"id": 1, "name": "Item 1"},
            {"id": 2, "name": "Item 2"},
        ]
        response = PaginatedResponse(
            items=items,
            total=2,
            page=1,
            page_size=10,
            total_pages=1,
        )
        
        assert len(response.items) == 2
        assert response.items[0]["id"] == 1
