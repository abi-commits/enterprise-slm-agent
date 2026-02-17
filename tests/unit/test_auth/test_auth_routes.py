"""Tests for Auth Service routes."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.models.user import UserRole
from services.api.schemas import LoginRequest, LoginResponse
from services.api.routers import auth


# Test constants
TEST_USER_ID = "12345678-1234-1234-1234-123456789012"
TEST_USERNAME = "testuser"
TEST_EMAIL = "testuser@example.com"
TEST_PASSWORD = "SecureP@ssw0rd!"
TEST_ROLE = UserRole.ADMIN


class MockUser:
    """Mock user object for testing."""
    
    def __init__(
        self,
        id: str = TEST_USER_ID,
        username: str = TEST_USERNAME,
        email: str = TEST_EMAIL,
        hashed_password: str = "$2b$12$hashed",
        role: UserRole = TEST_ROLE,
        is_active: bool = True,
    ):
        self.id = id
        self.username = username
        self.email = email
        self.hashed_password = hashed_password
        self.role = role
        self.is_active = is_active
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


class TestLoginEndpoint:
    """Test cases for the login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(self):
        """Test successful login."""
        # Create mock user
        mock_user = MockUser()
        
        # Create mock database
        mock_db = MagicMock()
        mock_db.get_user_by_username = AsyncMock(return_value=mock_user)
        
        # Create login request
        login_data = LoginRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )
        
        # Patch password verification
        with patch("services.api.routers.auth.verify_password", return_value=True):
            with patch("services.api.routers.auth.create_access_token") as mock_create_token:
                mock_create_token.return_value = "test-jwt-token"
                
                # Call the login endpoint
                response = await auth.login(login_data, mock_db)
                
                # Verify response
                assert isinstance(response, LoginResponse)
                assert response.access_token == "test-jwt-token"
                assert response.token_type == "bearer"
                assert response.user_id == TEST_USER_ID
                assert response.username == TEST_USERNAME
                assert response.role == TEST_ROLE.value

    @pytest.mark.asyncio
    async def test_login_user_not_found(self):
        """Test login with non-existent user."""
        # Create mock database
        mock_db = MagicMock()
        mock_db.get_user_by_username = AsyncMock(return_value=None)
        
        # Create login request
        login_data = LoginRequest(
            username="nonexistent",
            password=TEST_PASSWORD,
        )
        
        # Call the login endpoint and expect HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await auth.login(login_data, mock_db)
        
        assert exc_info.value.status_code == 401
        assert "Incorrect username or password" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_login_invalid_password(self):
        """Test login with invalid password."""
        # Create mock user
        mock_user = MockUser()
        
        # Create mock database
        mock_db = MagicMock()
        mock_db.get_user_by_username = AsyncMock(return_value=mock_user)
        
        # Create login request
        login_data = LoginRequest(
            username=TEST_USERNAME,
            password="wrong-password",
        )
        
        # Patch password verification to return False
        with patch("services.api.routers.auth.verify_password", return_value=False):
            # Call the login endpoint and expect HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await auth.login(login_data, mock_db)
            
            assert exc_info.value.status_code == 401
            assert "Incorrect username or password" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_login_inactive_user(self):
        """Test login with inactive user."""
        # Create mock user
        mock_user = MockUser(is_active=False)
        
        # Create mock database
        mock_db = MagicMock()
        mock_db.get_user_by_username = AsyncMock(return_value=mock_user)
        
        # Create login request
        login_data = LoginRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )
        
        # Patch password verification
        with patch("services.api.routers.auth.verify_password", return_value=True):
            # Call the login endpoint and expect HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await auth.login(login_data, mock_db)
            
            assert exc_info.value.status_code == 403
            assert "User account is disabled" in exc_info.value.detail


class TestLoginRequestValidation:
    """Test cases for LoginRequest validation."""

    def test_login_request_valid(self):
        """Test LoginRequest with valid data."""
        request = LoginRequest(
            username="testuser",
            password="password123",
        )
        
        assert request.username == "testuser"
        assert request.password == "password123"

    def test_login_request_username_required(self):
        """Test LoginRequest requires username."""
        with pytest.raises(ValueError):
            LoginRequest(password="password123")

    def test_login_request_password_required(self):
        """Test LoginRequest requires password."""
        with pytest.raises(ValueError):
            LoginRequest(username="testuser")


class TestLoginResponse:
    """Test cases for LoginResponse model."""

    def test_login_response_defaults(self):
        """Test LoginResponse with default values."""
        response = LoginResponse(
            access_token="test-token",
            user_id=TEST_USER_ID,
            username=TEST_USERNAME,
            role=TEST_ROLE.value,
        )
        
        assert response.token_type == "bearer"

    def test_login_response_custom(self):
        """Test LoginResponse with custom values."""
        response = LoginResponse(
            access_token="test-token",
            token_type="bearer",
            user_id=TEST_USER_ID,
            username=TEST_USERNAME,
            role=TEST_ROLE.value,
        )
        
        assert response.token_type == "bearer"
        assert response.access_token == "test-token"
