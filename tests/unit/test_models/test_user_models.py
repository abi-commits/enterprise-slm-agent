"""Tests for Pydantic user models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from core.models.user import (
    UserRole,
    UserBase,
    UserCreate,
    UserInDB,
    User,
    Token,
    TokenData,
    LoginRequest,
    ValidateTokenRequest,
)


class TestUserRole:
    """Test cases for UserRole enum."""

    def test_user_role_values(self):
        """Test UserRole enum values."""
        assert UserRole.ADMIN.value == "Admin"
        assert UserRole.HR.value == "HR"
        assert UserRole.ENGINEERING.value == "Engineering"
        assert UserRole.FINANCE.value == "Finance"
        assert UserRole.OPERATIONS.value == "Operations"


class TestUserBase:
    """Test cases for UserBase model."""

    def test_user_base_valid(self):
        """Test UserBase with valid data."""
        user = UserBase(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            role=UserRole.ENGINEERING,
        )
        
        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.full_name == "Test User"
        assert user.role == UserRole.ENGINEERING

    def test_user_base_defaults(self):
        """Test UserBase with default values."""
        user = UserBase(
            email="test@example.com",
            username="testuser",
        )
        
        assert user.full_name is None
        assert user.role == UserRole.OPERATIONS

    def test_user_base_invalid_email(self):
        """Test UserBase with invalid email."""
        with pytest.raises(ValidationError):
            UserBase(
                email="not-an-email",
                username="testuser",
            )

    def test_user_base_username_too_short(self):
        """Test UserBase with username too short."""
        with pytest.raises(ValidationError):
            UserBase(
                email="test@example.com",
                username="ab",  # Less than 3 characters
            )

    def test_user_base_username_too_long(self):
        """Test UserBase with username too long."""
        with pytest.raises(ValidationError):
            UserBase(
                email="test@example.com",
                username="a" * 51,  # More than 50 characters
            )


class TestUserCreate:
    """Test cases for UserCreate model."""

    def test_user_create_valid(self):
        """Test UserCreate with valid data."""
        user = UserCreate(
            email="test@example.com",
            username="testuser",
            password="SecureP@ss123",
            full_name="Test User",
            role=UserRole.HR,
        )
        
        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.password == "SecureP@ss123"
        assert user.full_name == "Test User"
        assert user.role == UserRole.HR

    def test_user_create_password_too_short(self):
        """Test UserCreate with password too short."""
        with pytest.raises(ValidationError):
            UserCreate(
                email="test@example.com",
                username="testuser",
                password="short",
            )

    def test_user_create_password_too_long(self):
        """Test UserCreate with password too long."""
        with pytest.raises(ValidationError):
            UserCreate(
                email="test@example.com",
                username="testuser",
                password="a" * 101,
            )


class TestUserInDB:
    """Test cases for UserInDB model."""

    def test_user_in_db_valid(self):
        """Test UserInDB with valid data."""
        user = UserInDB(
            id="12345678-1234-1234-1234-123456789012",
            email="test@example.com",
            username="testuser",
            hashed_password="$2b$12$hashed",
            full_name="Test User",
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        assert user.id == "12345678-1234-1234-1234-123456789012"
        assert user.is_active is True

    def test_user_in_db_defaults(self):
        """Test UserInDB with default values."""
        now = datetime.utcnow()
        user = UserInDB(
            id="12345678-1234-1234-1234-123456789012",
            email="test@example.com",
            username="testuser",
            hashed_password="$2b$12$hashed",
            created_at=now,
            updated_at=now,
        )
        
        assert user.is_active is True
        assert user.role == UserRole.OPERATIONS


class TestUser:
    """Test cases for User public model."""

    def test_user_valid(self):
        """Test User with valid data."""
        user = User(
            id="12345678-1234-1234-1234-123456789012",
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            role=UserRole.ENGINEERING,
            is_active=True,
            created_at=datetime.utcnow(),
        )
        
        assert user.id == "12345678-1234-1234-1234-123456789012"
        assert user.is_active is True

    def test_user_from_attributes(self):
        """Test User creation from attributes."""
        now = datetime.utcnow()
        user = User(
            id="12345678-1234-1234-1234-123456789012",
            email="test@example.com",
            username="testuser",
            role=UserRole.OPERATIONS,
            is_active=True,
            created_at=now,
        )
        
        assert user.full_name is None


class TestToken:
    """Test cases for Token model."""

    def test_token_default(self):
        """Test Token with default values."""
        token = Token(access_token="test-token")
        
        assert token.access_token == "test-token"
        assert token.token_type == "bearer"

    def test_token_custom(self):
        """Test Token with custom values."""
        token = Token(
            access_token="test-token",
            token_type="bearer",
        )
        
        assert token.token_type == "bearer"


class TestTokenData:
    """Test cases for TokenData model."""

    def test_token_data_optional(self):
        """Test TokenData with optional fields."""
        token_data = TokenData()
        
        assert token_data.user_id is None
        assert token_data.username is None
        assert token_data.role is None

    def test_token_data_full(self):
        """Test TokenData with all fields."""
        token_data = TokenData(
            user_id="12345678-1234-1234-1234-123456789012",
            username="testuser",
            role=UserRole.ADMIN,
        )
        
        assert token_data.user_id == "12345678-1234-1234-1234-123456789012"
        assert token_data.username == "testuser"
        assert token_data.role == UserRole.ADMIN


class TestLoginRequest:
    """Test cases for LoginRequest model."""

    def test_login_request_valid(self):
        """Test LoginRequest with valid data."""
        request = LoginRequest(
            username="testuser",
            password="password123",
        )
        
        assert request.username == "testuser"
        assert request.password == "password123"


class TestValidateTokenRequest:
    """Test cases for ValidateTokenRequest model."""

    def test_validate_token_request_valid(self):
        """Test ValidateTokenRequest with valid data."""
        request = ValidateTokenRequest(token="test-token")
        
        assert request.token == "test-token"
