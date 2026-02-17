"""Pytest configuration and shared fixtures for all tests."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from core.config.settings import get_settings, Settings
from core.models.user import UserInDB, UserRole


# Apply async mode for pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_settings() -> Settings:
    """Get test settings with appropriate defaults."""
    settings = Settings(
        environment="testing",
        debug=True,
        database_url="postgresql+asyncpg://test_user:test_pass@localhost:5432/test_db",
        redis_url="redis://localhost:6379/1",
        jwt_secret_key="test-secret-key-do-not-use-in-production",
    )
    return settings


@pytest.fixture
def mock_settings(test_settings) -> MagicMock:
    """Fixture for mocked settings."""
    mock = MagicMock(spec=Settings)
    for key, value in test_settings.__dict__.items():
        setattr(mock, key, value)
    return mock


@pytest.fixture
def test_user_data() -> dict:
    """Fixture for test user data."""
    return {
        "id": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "hashed_password": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.Z.K9mRENYs.1lq",
        "full_name": "Test User",
        "role": UserRole.USER,
        "is_active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def admin_user_data() -> dict:
    """Fixture for admin user data."""
    return {
        "id": "admin-user-123",
        "username": "adminuser",
        "email": "admin@example.com",
        "hashed_password": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.Z.K9mRENYs.1lq",
        "full_name": "Admin User",
        "role": UserRole.ADMIN,
        "is_active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }


@pytest.fixture
def mock_http_client() -> AsyncMock:
    """Fixture for mocked HTTP client."""
    return AsyncMock()


@pytest.fixture
def mock_async_context_manager():
    """Fixture for async context managers."""
    
    class AsyncContextManager:
        def __init__(self, return_value=None):
            self.return_value = return_value
        
        async def __aenter__(self):
            return self.return_value
        
        async def __aexit__(self, *args):
            pass
    
    return AsyncContextManager
