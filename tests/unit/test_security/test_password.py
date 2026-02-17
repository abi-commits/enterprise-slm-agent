"""Tests for password hashing and verification."""

import pytest
from unittest.mock import patch

from core.security.password import get_password_hash, verify_password


class TestPasswordHashing:
    """Test cases for password hashing functions."""

    def test_get_password_hash_returns_string(self):
        """Test that get_password_hash returns a non-empty string."""
        password = "SecureP@ssw0rd!"
        hashed = get_password_hash(password)
        
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_get_password_hash_is_bcrypt(self):
        """Test that hashed password uses bcrypt format."""
        password = "TestPassword123"
        hashed = get_password_hash(password)
        
        # Bcrypt hashes start with $2b$, $2a$, or $2y$
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_get_password_hash_different_hashes(self):
        """Test that same password produces different hashes (salt)."""
        password = "SamePassword"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        
        # Bcrypt includes random salt, so hashes should be different
        assert hash1 != hash2

    def test_verify_password_correct_password(self):
        """Test password verification with correct password."""
        password = "SecureP@ssw0rd!"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect_password(self):
        """Test password verification with incorrect password."""
        password = "SecureP@ssw0rd!"
        hashed = get_password_hash(password)
        
        assert verify_password("WrongPassword", hashed) is False

    def test_verify_password_empty_password(self):
        """Test password verification with empty password."""
        password = "SecureP@ssw0rd!"
        hashed = get_password_hash(password)
        
        assert verify_password("", hashed) is False

    def test_verify_password_none_plain(self):
        """Test password verification with None plain password."""
        password = "SecureP@ssw0rd!"
        hashed = get_password_hash(password)
        
        with pytest.raises(TypeError):
            verify_password(None, hashed)  # type: ignore

    def test_verify_password_none_hashed(self):
        """Test password verification with None hashed password."""
        with pytest.raises(TypeError):
            verify_password("password", None)  # type: ignore


class TestPasswordContext:
    """Test cases for password context configuration."""

    def test_password_context_exists(self):
        """Test that password context is properly configured."""
        from core.security.password import pwd_context
        
        assert pwd_context is not None

    def test_password_context_uses_bcrypt(self):
        """Test that password context uses bcrypt scheme."""
        from core.security.password import pwd_context
        
        # Check that bcrypt is in the schemes
        assert "bcrypt" in pwd_context.schemes
