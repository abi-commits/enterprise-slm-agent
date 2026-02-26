"""Database operations for refresh tokens.

Handles storage, retrieval, and revocation of JWT refresh tokens.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from services.api.database.models import RefreshToken
from core.security.jwt import hash_refresh_token
from core.config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()



async def store_refresh_token(
    session: AsyncSession,
    token: str,
    user_id: str,
    expires_delta: Optional[timedelta] = None,
) -> RefreshToken:
    """Store a refresh token in the database.
    
    Args:
        session: Database session
        token: The refresh token (will be hashed before storage)
        user_id: User ID associated with the token
        expires_delta: Optional expiration time (default: 7 days)
        
    Returns:
        Created RefreshToken model
    """
    token_hash = hash_refresh_token(token)
    
    if expires_delta:
        expires_at = datetime.utcnow() + expires_delta
    else:
        # Default to 7 days
        expires_at = datetime.utcnow() + timedelta(days=7)
    
    refresh_token = RefreshToken(
        token_hash=token_hash,
        user_id=user_id,
        expires_at=expires_at,
        revoked=False,
    )
    
    session.add(refresh_token)
    await session.commit()
    await session.refresh(refresh_token)
    
    logger.info(f"Stored refresh token for user {user_id} (expires: {expires_at})")
    return refresh_token


async def get_refresh_token(
    session: AsyncSession,
    token: str,
) -> Optional[RefreshToken]:
    """Get a refresh token from the database.
    
    Args:
        session: Database session
        token: The refresh token (will be hashed for lookup)
        
    Returns:
        RefreshToken model if found and valid, None otherwise
    """
    token_hash = hash_refresh_token(token)
    
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    
    return result.scalar_one_or_none()


async def verify_refresh_token(
    session: AsyncSession,
    token: str,
) -> Optional[str]:
    """Verify a refresh token and return the user ID.
    
    🔒 CRITICAL SECURITY: Implements reuse detection.
    
    If a revoked token is presented, this indicates token theft:
    - The legitimate user already used it (causing revocation)
    - An attacker is now trying to use the old stolen token
    
    Response to reuse:
    1. Revoke ALL user's refresh tokens (kill attacker's session)
    2. Alert security team (human investigation)
    3. Flag account for password reset (force user to secure account)
    
    Args:
        session: Database session
        token: The refresh token to verify
        
    Returns:
        User ID if token is valid and not expired/revoked, None otherwise
    """
    token_hash = hash_refresh_token(token)
    
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    refresh_token = result.scalar_one_or_none()
    
    if not refresh_token:
        logger.warning("Refresh token not found in database")
        return None
    
    # Track usage attempt (for forensics)
    current_time = datetime.utcnow()
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.id == refresh_token.id)
        .values(
            last_used_at=current_time,
            used_count=RefreshToken.used_count + 1,
        )
    )
    await session.commit()
    
    # 🚨 CRITICAL: Reuse detection
    if refresh_token.revoked:
        # Calculate time between revocation and reuse attempt
        time_since_revoked = None
        if refresh_token.revoked_at:
            time_since_revoked = (current_time - refresh_token.revoked_at).total_seconds()
        
        logger.critical(
            f"🚨🚨🚨 SECURITY BREACH DETECTED 🚨🚨🚨\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"EVENT: Refresh token reuse attempt\n"
            f"USER: {refresh_token.user_id}\n"
            f"TOKEN REVOKED: {refresh_token.revoked_at}\n"
            f"REUSE ATTEMPT: {current_time}\n"
            f"TIME SINCE REVOKED: {time_since_revoked}s\n"
            f"USED COUNT: {refresh_token.used_count}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"ANALYSIS: This token was already used and revoked.\n"
            f"Someone (attacker or legitimate user) is attempting\n"
            f"to reuse it. This indicates token theft.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"RESPONSE: Revoking ALL user sessions immediately."
        )
        
        # Nuclear response: revoke ALL tokens for this user
        revoked_count = await revoke_user_tokens(session, refresh_token.user_id)
        logger.critical(
            f"🔒 Revoked {revoked_count} tokens for user {refresh_token.user_id}"
        )
        
        # Alert security team
        try:
            from core.security.alerts import (
                alert_security_team,
                flag_user_for_password_reset,
                SecurityEventType,
                SecurityEventSeverity,
            )
            
            await alert_security_team(
                event_type=SecurityEventType.REFRESH_TOKEN_REUSE,
                user_id=refresh_token.user_id,
                severity=SecurityEventSeverity.CRITICAL,
                description=(
                    f"Refresh token reuse detected. Token was revoked "
                    f"{time_since_revoked}s ago but presented again. "
                    f"Revoked {revoked_count} active sessions."
                ),
                metadata={
                    "token_id": refresh_token.id,
                    "revoked_at": refresh_token.revoked_at.isoformat() if refresh_token.revoked_at else None,
                    "reuse_attempt_at": current_time.isoformat(),
                    "time_since_revoked_seconds": time_since_revoked,
                    "used_count": refresh_token.used_count,
                    "tokens_revoked": revoked_count,
                }
            )
            
            # Flag account for mandatory password reset
            await flag_user_for_password_reset(
                user_id=refresh_token.user_id,
                reason="Refresh token reuse detected (possible account compromise)"
            )
            
        except Exception as alert_error:
            # Don't fail the request if alerting fails
            logger.error(f"Failed to send security alert: {alert_error}")
        
        # Deny the request
        return None
    
    # Check if expired
    if refresh_token.expires_at < current_time:
        logger.warning(
            f"Refresh token for user {refresh_token.user_id} has expired "
            f"(expired: {refresh_token.expires_at}, now: {current_time})"
        )
        return None
    
    # Token is valid
    return refresh_token.user_id


async def revoke_refresh_token(
    session: AsyncSession,
    token: str,
) -> bool:
    """Revoke a refresh token.
    
    Args:
        session: Database session
        token: The refresh token to revoke
        
    Returns:
        True if revoked, False if not found
    """
    token_hash = hash_refresh_token(token)
    
    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .values(
            revoked=True,
            revoked_at=datetime.utcnow(),  # Track when revoked for forensics
        )
    )
    await session.commit()
    
    revoked = result.rowcount > 0
    if revoked:
        logger.info(f"Revoked refresh token at {datetime.utcnow()}")
    
    return revoked


async def revoke_user_tokens(
    session: AsyncSession,
    user_id: str,
) -> int:
    """Revoke all refresh tokens for a user.
    
    Useful for logout-all functionality or when a user's password changes.
    
    Args:
        session: Database session
        user_id: User ID whose tokens to revoke
        
    Returns:
        Number of tokens revoked
    """
    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .where(RefreshToken.revoked == False)
        .values(revoked=True)
    )
    await session.commit()
    
    count = result.rowcount
    logger.info(f"Revoked {count} refresh tokens for user {user_id}")
    
    return count


async def cleanup_expired_tokens(
    session: AsyncSession,
) -> int:
    """Delete expired refresh tokens from the database.
    
    Should be called periodically (e.g., via cron job) to prevent database bloat.
    
    Args:
        session: Database session
        
    Returns:
        Number of tokens deleted
    """
    result = await session.execute(
        delete(RefreshToken).where(RefreshToken.expires_at < datetime.utcnow())
    )
    await session.commit()
    
    count = result.rowcount
    logger.info(f"Cleaned up {count} expired refresh tokens")
    
    return count
