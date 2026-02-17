"""Tests for JWT token creation and verification."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from jose import jwt

from core.security.jwt import create_access_token, verify_token, decode_token, TokenData


# Test constants
TEST_SECRET_KEY = "test-secret-key-for-testing"
TEST_ALGORITHM = "HS256"
TEST_USER_ID = "12345678-1234-1234-1234-123456789012"
TEST_ROLE = "Admin"


class TestCreateAccessToken:
    """Test cases for JWT token creation."""

    @patch("core.security.jwt.settings")
    def test_create_access_token_returns_string(self, mock_settings):
        """Test that create_access_token returns a JWT string."""
        mock_settings.jwt_secret_key = TEST_SECRET_KEY
        mock_settings.jwt_algorithm = TEST_ALGORITHM
        mock_settings.access_token_expire_minutes = 30
        
        data = {"sub": TEST_USER_ID, "role": TEST_ROLE}
        token = create_access_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0

    @patch("core.security.jwt.settings")
    def test_create_access_token_contains_payload(self, mock_settings):
        """Test that token contains the expected payload."""
        mock_settings.jwt_secret_key = TEST_SECRET_KEY
        mock_settings.jwt_algorithm = TEST_ALGORITHM
        mock_settings.access_token_expire_minutes = 30
        
        data = {"sub": TEST_USER_ID, "role": TEST_ROLE}
        token = create_access_token(data)
        
        # Decode without verification to check payload
        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=[TEST_ALGORITHM], options={"verify_signature": False})
        
        assert payload["sub"] == TEST_USER_ID
        assert payload["role"] == TEST_ROLE
        assert "exp" in payload

    @patch("core.security.jwt.settings")
    def test_create_access_token_with_custom_expiry(self, mock_settings):
        """Test token creation with custom expiration."""
        mock_settings.jwt_secret_key = TEST_SECRET_KEY
        mock_settings.jwt_algorithm = TEST_ALGORITHM
        mock_settings.access_token_expire_minutes = 30
        
        data = {"sub": TEST_USER_ID, "role": TEST_ROLE}
        custom_delta = timedelta(hours=1)
        token = create_access_token(data, expires_delta=custom_delta)
        
        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=[TEST_ALGORITHM], options={"verify_signature": False})
        
        # Check expiration is approximately 1 hour from now
        exp_time = datetime.fromisoformat(payload["exp"].replace("Z", "+00:00"))
        expected_exp = datetime.now(timezone.utc) + custom_delta
        
        # Allow 5 second tolerance
        assert abs((exp_time - expected_exp).total_seconds()) < 5

    @patch("core.security.jwt.settings")
    def test_create_access_token_default_expiry(self, mock_settings):
        """Test token creation with default expiration from settings."""
        mock_settings.jwt_secret_key = TEST_SECRET_KEY
        mock_settings.jwt_algorithm = TEST_ALGORITHM
        mock_settings.access_token_expire_minutes = 30
        
        data = {"sub": TEST_USER_ID, "role": TEST_ROLE}
        token = create_access_token(data)
        
        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=[TEST_ALGORITHM], options={"verify_signature": False})
        
        # Check expiration is approximately 30 minutes from now
        exp_time = datetime.fromisoformat(payload["exp"].replace("Z", "+00:00"))
        expected_exp = datetime.now(timezone.utc) + timedelta(minutes=30)
        
        # Allow 5 second tolerance
        assert abs((exp_time - expected_exp).total_seconds()) < 5


class TestVerifyToken:
    """Test cases for JWT token verification."""

    @patch("core.security.jwt.settings")
    def test_verify_token_valid_token(self, mock_settings):
        """Test verification of a valid token."""
        mock_settings.jwt_secret_key = TEST_SECRET_KEY
        mock_settings.jwt_algorithm = TEST_ALGORITHM
        mock_settings.access_token_expire_minutes = 30
        
        # Create a valid token
        data = {"sub": TEST_USER_ID, "role": TEST_ROLE}
        token = create_access_token(data)
        
        # Verify it
        result = verify_token(token)
        
        assert result is not None
        assert result.sub == TEST_USER_ID
        assert result.role == TEST_ROLE

    @patch("core.security.jwt.settings")
    def test_verify_token_invalid_signature(self, mock_settings):
        """Test verification of token with invalid signature."""
        mock_settings.jwt_secret_key = TEST_SECRET_KEY
        mock_settings.jwt_algorithm = TEST_ALGORITHM
        
        # Create token with different secret
        data = {"sub": TEST_USER_ID, "role": TEST_ROLE}
        token = jwt.encode(data, "wrong-secret-key", algorithm=TEST_ALGORITHM)
        
        result = verify_token(token)
        
        assert result is None

    @patch("core.security.jwt.settings")
    def test_verify_token_expired(self, mock_settings):
        """Test verification of expired token."""
        mock_settings.jwt_secret_key = TEST_SECRET_KEY
        mock_settings.jwt_algorithm = TEST_ALGORITHM
        
        # Create expired token
        payload = {
            "sub": TEST_USER_ID,
            "role": TEST_ROLE,
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = jwt.encode(payload, TEST_SECRET_KEY, algorithm=TEST_ALGORITHM)
        
        result = verify_token(token)
        
        assert result is None

    @patch("core.security.jwt.settings")
    def test_verify_token_missing_sub(self, mock_settings):
        """Test verification of token missing subject."""
        mock_settings.jwt_secret_key = TEST_SECRET_KEY
        mock_settings.jwt_algorithm = TEST_ALGORITHM
        
        # Create token without 'sub' claim
        payload = {
            "role": TEST_ROLE,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, TEST_SECRET_KEY, algorithm=TEST_ALGORITHM)
        
        result = verify_token(token)
        
        assert result is None

    @patch("core.security.jwt.settings")
    def test_verify_token_missing_role(self, mock_settings):
        """Test verification of token missing role."""
        mock_settings.jwt_secret_key = TEST_SECRET_KEY
        mock_settings.jwt_algorithm = TEST_ALGORITHM
        
        # Create token without 'role' claim
        payload = {
            "sub": TEST_USER_ID,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, TEST_SECRET_KEY, algorithm=TEST_ALGORITHM)
        
        result = verify_token(token)
        
        assert result is None

    @patch("core.security.jwt.settings")
    def test_verify_token_invalid_token(self, mock_settings):
        """Test verification of invalid token string."""
        mock_settings.jwt_secret_key = TEST_SECRET_KEY
        mock_settings.jwt_algorithm = TEST_ALGORITHM
        
        result = verify_token("not-a-valid-token")
        
        assert result is None


class TestDecodeToken:
    """Test cases for JWT token decoding without verification."""

    @patch("core.security.jwt.settings")
    def test_decode_token_valid(self, mock_settings):
        """Test decoding a valid token."""
        mock_settings.jwt_secret_key = TEST_SECRET_KEY
        mock_settings.jwt_algorithm = TEST_ALGORITHM
        
        data = {"sub": TEST_USER_ID, "role": TEST_ROLE}
        token = create_access_token(data)
        
        result = decode_token(token)
        
        assert result is not None
        assert result["sub"] == TEST_USER_ID
        assert result["role"] == TEST_ROLE

    @patch("core.security.jwt.settings")
    def test_decode_token_invalid(self, mock_settings):
        """Test decoding an invalid token."""
        mock_settings.jwt_secret_key = TEST_SECRET_KEY
        mock_settings.jwt_algorithm = TEST_ALGORITHM
        
        result = decode_token("invalid-token")
        
        assert result is None


class TestTokenData:
    """Test cases for TokenData model."""

    def test_token_data_model(self):
        """Test TokenData model creation."""
        token_data = TokenData(sub=TEST_USER_ID, role=TEST_ROLE)
        
        assert token_data.sub == TEST_USER_ID
        assert token_data.role == TEST_ROLE
        assert token_data.exp is None

    def test_token_data_with_expiry(self):
        """Test TokenData with expiration."""
        exp = datetime.now(timezone.utc)
        token_data = TokenData(sub=TEST_USER_ID, role=TEST_ROLE, exp=exp)
        
        assert token_data.exp == exp
