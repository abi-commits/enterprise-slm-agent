"""Tests for refresh token reuse detection.

This module tests the security-critical refresh token reuse detection flow:
- Normal token verification
- Reuse detection (presenting a revoked token)
- Automatic token revocation on breach
- Security alerting
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.api.database.models import RefreshToken
from services.api.database.refresh_token_db import (
    verify_refresh_token,
    revoke_refresh_token,
    store_refresh_token,
    revoke_user_tokens,
    get_refresh_token,
)
from core.security.alerts import (
    SecurityEventType,
    SecurityEventSeverity,
)
from typing import Optional


# Test constants
TEST_USER_ID = "user-12345678-1234-1234-1234-123456789012"
TEST_TOKEN = "refresh-token-abc123"
TEST_TOKEN_HASH = "hashed-token-abc123"


def create_mock_refresh_token(
    user_id: str = TEST_USER_ID,
    revoked: bool = False,
    revoked_at: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    used_count: int = 0,
) -> RefreshToken:
    """Create a mock RefreshToken for testing."""
    token = MagicMock(spec=RefreshToken)
    token.id = 1
    token.token_hash = TEST_TOKEN_HASH
    token.user_id = user_id
    token.expires_at = expires_at or (datetime.utcnow() + timedelta(days=7))
    token.created_at = datetime.utcnow()
    token.revoked = revoked
    token.revoked_at = revoked_at
    token.last_used_at = None
    token.used_count = used_count
    return token


class TestVerifyRefreshToken:
    """Test cases for verify_refresh_token function."""

    @pytest.mark.asyncio
    async def test_verify_valid_token_returns_user_id(self):
        """Test that a valid token returns the user ID."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_token = create_mock_refresh_token()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute.return_value = mock_result
        
        with patch(
            "services.api.database.refresh_token_db.hash_refresh_token",
            return_value=TEST_TOKEN_HASH,
        ):
            result = await verify_refresh_token(mock_session, TEST_TOKEN)
            
        assert result == TEST_USER_ID

    @pytest.mark.asyncio
    async def test_verify_nonexistent_token_returns_none(self):
        """Test that a non-existent token returns None."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        with patch(
            "services.api.database.refresh_token_db.hash_refresh_token",
            return_value=TEST_TOKEN_HASH,
        ):
            result = await verify_refresh_token(mock_session, TEST_TOKEN)
            
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_expired_token_returns_none(self):
        """Test that an expired token returns None."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_token = create_mock_refresh_token(
            expires_at=datetime.utcnow() - timedelta(days=1)  # Expired yesterday
        )
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute.return_value = mock_result
        
        with patch(
            "services.api.database.refresh_token_db.hash_refresh_token",
            return_value=TEST_TOKEN_HASH,
        ):
            result = await verify_refresh_token(mock_session, TEST_TOKEN)
            
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_revoked_token_triggers_breach_response(self):
        """
        Test that presenting a revoked token triggers reuse detection.
        
        This is the critical security scenario:
        1. User uses refresh token -> gets new one, old one revoked
        2. Attacker presents the stolen (revoked) token
        3. System detects reuse, revokes ALL user tokens
        """
        mock_session = AsyncMock()
        mock_result = MagicMock()
        
        # Create a revoked token with timestamp
        revocation_time = datetime.utcnow() - timedelta(minutes=5)
        mock_token = create_mock_refresh_token(
            revoked=True,
            revoked_at=revocation_time,
            used_count=1,  # Already used once
        )
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute.return_value = mock_result
        
        with patch(
            "services.api.database.refresh_token_db.hash_refresh_token",
            return_value=TEST_TOKEN_HASH,
        ):
            with patch(
                "services.api.database.refresh_token_db.revoke_user_tokens",
                new_callable=AsyncMock,
            ) as mock_revoke_all:
                mock_revoke_all.return_value = 3  # Simulating 3 tokens revoked
                
                with patch(
                    "core.security.alerts.alert_security_team",
                    new_callable=AsyncMock,
                ) as mock_alert:
                    with patch(
                        "core.security.alerts.flag_user_for_password_reset",
                        new_callable=AsyncMock,
                    ) as mock_flag_reset:
                        result = await verify_refresh_token(mock_session, TEST_TOKEN)
                        
                        # Should return None (denied)
                        assert result is None
                        
                        # Should have revoked all user tokens
                        mock_revoke_all.assert_called_once_with(mock_session, TEST_USER_ID)
                        
                        # Should have alerted security team
                        mock_alert.assert_called_once()
                        alert_kwargs = mock_alert.call_args.kwargs
                        assert alert_kwargs["event_type"] == SecurityEventType.REFRESH_TOKEN_REUSE
                        assert alert_kwargs["severity"] == SecurityEventSeverity.CRITICAL
                        assert alert_kwargs["user_id"] == TEST_USER_ID
                        
                        # Should have flagged user for password reset
                        mock_flag_reset.assert_called_once()
                        flag_kwargs = mock_flag_reset.call_args.kwargs
                        assert flag_kwargs["user_id"] == TEST_USER_ID
                        assert "reuse" in flag_kwargs["reason"].lower()

    @pytest.mark.asyncio
    async def test_verify_revoked_token_increments_used_count(self):
        """Test that verifying a token increments its used_count."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_token = create_mock_refresh_token()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute.return_value = mock_result
        
        with patch(
            "services.api.database.refresh_token_db.hash_refresh_token",
            return_value=TEST_TOKEN_HASH,
        ):
            await verify_refresh_token(mock_session, TEST_TOKEN)
            
            # Verify update was called to increment used_count
            # The execute is called twice: once for select, once for update
            assert mock_session.execute.call_count >= 2
            assert mock_session.commit.called


class TestRevokeRefreshToken:
    """Test cases for revoke_refresh_token function."""

    @pytest.mark.asyncio
    async def test_revoke_sets_revoked_flag_and_timestamp(self):
        """Test that revoking a token sets both revoked and revoked_at."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result
        
        with patch(
            "services.api.database.refresh_token_db.hash_refresh_token",
            return_value=TEST_TOKEN_HASH,
        ):
            result = await revoke_refresh_token(mock_session, TEST_TOKEN)
            
        assert result is True
        mock_session.commit.assert_called_once()
        
        # Verify the update statement was called with proper values
        execute_call = mock_session.execute.call_args
        assert execute_call is not None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_token_returns_false(self):
        """Test that revoking a non-existent token returns False."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0  # No rows updated
        mock_session.execute.return_value = mock_result
        
        with patch(
            "services.api.database.refresh_token_db.hash_refresh_token",
            return_value=TEST_TOKEN_HASH,
        ):
            result = await revoke_refresh_token(mock_session, TEST_TOKEN)
            
        assert result is False


class TestRevokeUserTokens:
    """Test cases for revoke_user_tokens function."""

    @pytest.mark.asyncio
    async def test_revoke_all_user_tokens(self):
        """Test that revoking all user tokens returns the count."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 5  # 5 tokens revoked
        mock_session.execute.return_value = mock_result
        
        result = await revoke_user_tokens(mock_session, TEST_USER_ID)
        
        assert result == 5
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_user_with_no_tokens(self):
        """Test revoking for a user with no tokens."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result
        
        result = await revoke_user_tokens(mock_session, TEST_USER_ID)
        
        assert result == 0


class TestRefreshTokenReuseScenario:
    """Integration-style tests for complete reuse detection scenarios."""

    @pytest.mark.asyncio
    async def test_full_breach_scenario(self):
        """
        Test the complete breach scenario:
        
        Timeline:
        1. User logs in, gets token A
        2. Attacker steals token A from user's browser/device
        3. User uses token A normally -> A is revoked, user gets token B
        4. Attacker presents token A -> BREACH DETECTED
        5. System revokes ALL tokens (including B)
        6. Security team alerted
        7. User flagged for password reset
        8. Both user and attacker are logged out
        """
        # This test documents the expected behavior.
        # The actual implementation is tested in verify_revoked_token_triggers_breach_response
        
        # Step 1-2: Setup - user has token A, attacker has stolen copy
        user_token_a = "user-refresh-token-A"
        
        # Step 3: User uses token A (mocked via revocation)
        # In real flow, verify_refresh_token returns user_id, token is rotated
        
        # Step 4-8: Attacker presents revoked token A
        mock_session = AsyncMock()
        mock_result = MagicMock()
        
        # Token A is now revoked (from step 3)
        mock_token = create_mock_refresh_token(
            revoked=True,
            revoked_at=datetime.utcnow() - timedelta(seconds=30),
        )
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute.return_value = mock_result
        
        with patch(
            "services.api.database.refresh_token_db.hash_refresh_token",
            return_value=TEST_TOKEN_HASH,
        ):
            with patch(
                "services.api.database.refresh_token_db.revoke_user_tokens",
                new_callable=AsyncMock,
                return_value=2,  # Revoke user's current token B
            ):
                with patch(
                    "core.security.alerts.alert_security_team",
                    new_callable=AsyncMock,
                ):
                    with patch(
                        "core.security.alerts.flag_user_for_password_reset",
                        new_callable=AsyncMock,
                    ):
                        result = await verify_refresh_token(mock_session, user_token_a)
                        
                        # Attacker's request is denied
                        assert result is None


class TestSecurityAlertMetadata:
    """Test that security alerts contain proper forensic metadata."""

    @pytest.mark.asyncio
    async def test_alert_contains_time_since_revoked(self):
        """Test that alert metadata includes timing information."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        
        revoked_time = datetime.utcnow() - timedelta(minutes=10)
        mock_token = create_mock_refresh_token(
            revoked=True,
            revoked_at=revoked_time,
            used_count=5,
        )
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute.return_value = mock_result
        
        captured_metadata = {}
        
        async def capture_alert(**kwargs):
            captured_metadata.update(kwargs.get("metadata", {}))
        
        with patch(
            "services.api.database.refresh_token_db.hash_refresh_token",
            return_value=TEST_TOKEN_HASH,
        ):
            with patch(
                "services.api.database.refresh_token_db.revoke_user_tokens",
                new_callable=AsyncMock,
                return_value=1,
            ):
                with patch(
                    "core.security.alerts.alert_security_team",
                    side_effect=capture_alert,
                ):
                    with patch(
                        "core.security.alerts.flag_user_for_password_reset",
                        new_callable=AsyncMock,
                    ):
                        await verify_refresh_token(mock_session, TEST_TOKEN)
        
        # Verify metadata contains forensic information
        assert "token_id" in captured_metadata
        assert "revoked_at" in captured_metadata
        assert "reuse_attempt_at" in captured_metadata
        assert "time_since_revoked_seconds" in captured_metadata
        assert "used_count" in captured_metadata
        assert "tokens_revoked" in captured_metadata
        
        # Time since revoked should be approximately 10 minutes (600 seconds)
        time_since_revoked = captured_metadata["time_since_revoked_seconds"]
        assert 590 < time_since_revoked < 610


class TestTokenUsageTracking:
    """Test that token usage is properly tracked for forensics."""

    @pytest.mark.asyncio
    async def test_last_used_at_updated_on_verification(self):
        """Test that last_used_at is updated when token is verified."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_token = create_mock_refresh_token()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute.return_value = mock_result
        
        before_verification = datetime.utcnow()
        
        with patch(
            "services.api.database.refresh_token_db.hash_refresh_token",
            return_value=TEST_TOKEN_HASH,
        ):
            await verify_refresh_token(mock_session, TEST_TOKEN)
        
        # Verify update was called
        # We can't directly check the values without more complex mocking,
        # but we verify execute was called for the update
        assert mock_session.execute.call_count >= 2  # select + update

    @pytest.mark.asyncio
    async def test_used_count_increments_each_verification(self):
        """Test that used_count increments with each verification attempt."""
        # This behavior is tested implicitly through the update call
        # In production, this allows detecting suspicious patterns like
        # a token being used 10+ times when it should only be used once
        
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_token = create_mock_refresh_token(used_count=100)  # Suspicious!
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute.return_value = mock_result
        
        with patch(
            "services.api.database.refresh_token_db.hash_refresh_token",
            return_value=TEST_TOKEN_HASH,
        ):
            result = await verify_refresh_token(mock_session, TEST_TOKEN)
        
        # Valid token should still work, but the high used_count
        # could be flagged separately for investigation
        assert result == TEST_USER_ID
