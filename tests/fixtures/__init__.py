"""Common test fixtures for unit tests."""

from datetime import datetime, timedelta
from typing import Any

import pytest
from unittest.mock import MagicMock


# Test user data
TEST_USER_ID = "12345678-1234-1234-1234-123456789012"
TEST_USERNAME = "testuser"
TEST_EMAIL = "testuser@example.com"
TEST_PASSWORD = "SecureP@ssw0rd!"
TEST_FULL_NAME = "Test User"
TEST_ROLE = "Operations"

# Test hashed password (bcrypt hash of "SecureP@ssw0rd!")
TEST_HASHED_PASSWORD = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.Z.K9mRENYs.1lq"


@pytest.fixture
def test_user_dict() -> dict[str, Any]:
    """Fixture for test user dictionary."""
    return {
        "id": TEST_USER_ID,
        "email": TEST_EMAIL,
        "username": TEST_USERNAME,
        "hashed_password": TEST_HASHED_PASSWORD,
        "full_name": TEST_FULL_NAME,
        "role": TEST_ROLE,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }


@pytest.fixture
def mock_user() -> MagicMock:
    """Fixture for a mock user object."""
    user = MagicMock()
    user.id = TEST_USER_ID
    user.email = TEST_EMAIL
    user.username = TEST_USERNAME
    user.hashed_password = TEST_HASHED_PASSWORD
    user.full_name = TEST_FULL_NAME
    user.role = TEST_ROLE
    user.is_active = True
    user.created_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    return user


@pytest.fixture
def test_token_data() -> dict[str, Any]:
    """Fixture for test token data."""
    return {
        "sub": TEST_USER_ID,
        "role": TEST_ROLE,
    }


@pytest.fixture
def test_login_request() -> dict[str, Any]:
    """Fixture for login request data."""
    return {
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
    }


@pytest.fixture
def test_login_response() -> dict[str, Any]:
    """Fixture for login response data."""
    return {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test_token",
        "token_type": "bearer",
        "user_id": TEST_USER_ID,
        "username": TEST_USERNAME,
        "role": TEST_ROLE,
    }


@pytest.fixture
def test_query_request() -> dict[str, Any]:
    """Fixture for gateway query request."""
    return {
        "query": "What is the company vacation policy?",
        "user_id": TEST_USER_ID,
        "session_id": "session-123",
    }


@pytest.fixture
def test_optimize_request() -> dict[str, Any]:
    """Fixture for query optimizer request."""
    return {
        "query": "vacation policy",
        "user_context": "User is in HR department",
    }


@pytest.fixture
def test_search_request() -> dict[str, Any]:
    """Fixture for search request."""
    return {
        "query": "vacation policy",
        "user_role": "HR",
        "top_k": 10,
        "filters": None,
    }


@pytest.fixture
def test_generate_request() -> dict[str, Any]:
    """Fixture for generator request."""
    return {
        "query": "What is the vacation policy?",
        "context_documents": [
            {
                "id": "doc-1",
                "content": "The company vacation policy allows 15 days per year.",
                "score": 0.95,
                "source": "HR handbook",
            }
        ],
        "user_role": "HR",
        "use_llm": True,
        "conversation_history": None,
    }


@pytest.fixture
def test_source_document() -> dict[str, Any]:
    """Fixture for a source document."""
    return {
        "document_id": "doc-123",
        "title": "HR Policy Document",
        "content": "The company vacation policy allows employees to take up to 15 days...",
        "score": 0.95,
        "metadata": {"author": "HR Team", "date": "2024-01-01"},
    }


@pytest.fixture
def test_search_results() -> list[dict[str, Any]]:
    """Fixture for search results."""
    return [
        {
            "id": "doc-1",
            "content": "The company vacation policy allows employees to take up to 15 days...",
            "score": 0.95,
            "metadata": {"author": "HR Team"},
            "source": "HR handbook",
        },
        {
            "id": "doc-2",
            "content": "PTO accrual happens on a monthly basis...",
            "score": 0.85,
            "metadata": {"author": "HR Team"},
            "source": "Employee handbook",
        },
    ]


@pytest.fixture
def test_context_documents() -> list[dict[str, Any]]:
    """Fixture for context documents."""
    return [
        {
            "content": "The company vacation policy allows employees to take up to 15 days of paid vacation per year.",
            "source": "HR Handbook",
            "score": 0.95,
        },
        {
            "content": "Employees can carry over up to 5 days of unused vacation to the next year.",
            "source": "HR Handbook",
            "score": 0.90,
        },
    ]


@pytest.fixture
def mock_settings() -> MagicMock:
    """Fixture for mock settings."""
    settings = MagicMock()
    settings.jwt_secret_key = "test-secret-key"
    settings.jwt_algorithm = "HS256"
    settings.access_token_expire_minutes = 30
    settings.postgres_user = "test_user"
    settings.postgres_password = "test_password"
    settings.postgres_db = "test_db"
    settings.database_url = "postgresql+asyncpg://test_user:test_password@localhost:5432/test_db"
    settings.redis_url = "redis://localhost:6379/0"
    settings.qdrant_url = "http://localhost:6333"
    settings.qdrant_collection = "documents"
    settings.embedding_model = "BAAI/bge-small-en-v1.5"
    settings.reranker_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    settings.llm_model = "Qwen/Qwen2.5-1.5B-Instruct"
    settings.vllm_url = "http://localhost:8000"
    settings.confidence_threshold = 0.6
    settings.cache_embedding_ttl = 86400
    settings.cache_search_ttl = 3600
    settings.cache_llm_response_ttl = 86400
    return settings


@pytest.fixture
def valid_jwt_token() -> str:
    """Generate a valid JWT token for testing."""
    from datetime import timezone
    from jose import jwt
    
    payload = {
        "sub": TEST_USER_ID,
        "role": TEST_ROLE,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, "test-secret-key", algorithm="HS256")


@pytest.fixture
def expired_jwt_token() -> str:
    """Generate an expired JWT token for testing."""
    from datetime import timezone
    from jose import jwt
    
    payload = {
        "sub": TEST_USER_ID,
        "role": TEST_ROLE,
        "exp": datetime.now(timezone.utc) - timedelta(minutes=30),
    }
    return jwt.encode(payload, "test-secret-key", algorithm="HS256")
