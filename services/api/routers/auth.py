"""Authentication router for the consolidated API Service.

Merges:
- services/auth/routers/auth.py (login endpoint)
- services/auth/routers/validate.py (token validation endpoint)

Fixes:
- Added missing Depends import that was absent in the original validate.py
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from core.config.settings import get_settings
from core.security.jwt import create_access_token, verify_token, TokenData
from core.security.password import verify_password
from services.api.database import Database, db, get_db
from services.api import schemas
from services.api.schemas import (
    LoginRequest,
    LoginResponse,
    ValidateTokenRequest,
    ValidateTokenResponse,
)
from services.api import prometheus

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    database: Database = Depends(get_db),
) -> LoginResponse:
    """
    Authenticate a user and return a JWT access token.

    Args:
        login_data: Login credentials (username and password)
        database: Database dependency

    Returns:
        LoginResponse with access token and user info

    Raises:
        HTTPException: If credentials are invalid
    """
    # Get user by username or email
    user = await database.get_user_by_username(login_data.username)

    if user is None:
        prometheus.record_auth_failure("user_not_found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password
    if not verify_password(login_data.password, user.hashed_password):
        prometheus.record_auth_failure("invalid_password")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        prometheus.record_auth_failure("inactive_user")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Create access token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.id, "role": user.role.value},
        expires_delta=access_token_expires,
    )
    
    # Create refresh token
    from core.security.jwt import create_refresh_token
    from services.api.database.refresh_token_db import store_refresh_token
    
    refresh_token = create_refresh_token(user.id)
    
    # Store refresh token in database (7-day expiry)
    await store_refresh_token(
        session=database.session,
        token=refresh_token,
        user_id=user.id,
        expires_delta=timedelta(days=7),
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
        role=user.role.value,
    )


@router.post("/validate", response_model=ValidateTokenResponse)
async def validate_token(
    request: ValidateTokenRequest,
    database: Database = Depends(get_db),
) -> ValidateTokenResponse:
    """
    Validate a JWT token and return user information.

    Args:
        request: Token validation request containing the JWT
        database: Database dependency

    Returns:
        ValidateTokenResponse with validation result and user info
    """
    # Verify the token
    token_data = verify_token(request.token)

    if token_data is None:
        return ValidateTokenResponse(
            valid=False,
            user_id=None,
            username=None,
            role=None,
        )

    # Get user from database to verify they still exist and are active
    user = await database.get_user_by_id(token_data.sub)

    if user is None or not user.is_active:
        return ValidateTokenResponse(
            valid=False,
            user_id=None,
            username=None,
            role=None,
        )

    return ValidateTokenResponse(
        valid=True,
        user_id=token_data.sub,
        username=user.username,
        role=token_data.role,
    )


async def get_current_user(token: str = Depends(oauth2_scheme)) -> ValidateTokenResponse:
    """
    Dependency to get the current authenticated user from token.

    This performs IN-PROCESS token validation by calling core.security.jwt.verify_token
    directly, then looking up the user from the database. No HTTP call needed.

    Args:
        token: JWT token from Authorization header

    Returns:
        User information from validated token

    Raises:
        HTTPException: If token is invalid or user not found
    """
    # Verify token in-process (no HTTP call to auth service)
    token_data = verify_token(token)

    if token_data is None:
        prometheus.record_auth_failure("invalid_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Look up user directly from in-process database
    user = await db.get_user_by_id(token_data.sub)

    if user is None or not user.is_active:
        prometheus.record_auth_failure("user_not_found_or_inactive")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return ValidateTokenResponse(
        valid=True,
        user_id=token_data.sub,
        username=user.username,
        role=token_data.role,
    )


@router.post("/refresh", response_model=schemas.RefreshTokenResponse)
async def refresh_access_token(
    request: schemas.RefreshTokenRequest,
    database: Database = Depends(get_db),
) -> schemas.RefreshTokenResponse:
    """
    Refresh an access token using a refresh token.
    
    This endpoint verifies the refresh token and issues a new access token
    and a new refresh token. The old refresh token is revoked to prevent reuse.
    
    Args:
        request: Refresh token request containing the refresh token
        database: Database dependency
        
    Returns:
        RefreshTokenResponse with new access and refresh tokens
        
    Raises:
        HTTPException: If refresh token is invalid, expired, or revoked
    """
    from core.security.jwt import create_refresh_token
    from services.api.database.refresh_token_db import (
        verify_refresh_token,
        revoke_refresh_token,
        store_refresh_token,
    )
    
    # Verify refresh token
    user_id = await verify_refresh_token(database.session, request.refresh_token)
    
    if not user_id:
        prometheus.record_auth_failure("invalid_refresh_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    
    # Get user to verify they're still active
    user = await database.get_user_by_id(user_id)
    
    if not user or not user.is_active:
        prometheus.record_auth_failure("user_not_found_or_inactive")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    # Revoke old refresh token (token rotation for security)
    await revoke_refresh_token(database.session, request.refresh_token)
    
    # Create new access token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.id, "role": user.role.value},
        expires_delta=access_token_expires,
    )
    
    # Create new refresh token
    new_refresh_token = create_refresh_token(user.id)
    
    # Store new refresh token
    await store_refresh_token(
        session=database.session,
        token=new_refresh_token,
        user_id=user.id,
        expires_delta=timedelta(days=7),
    )
    
    logger.info(f"Refreshed access token for user {user.id}")
    
    return schemas.RefreshTokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@router.post("/logout", response_model=schemas.LogoutResponse)
async def logout(
    request: schemas.LogoutRequest,
    database: Database = Depends(get_db),
) -> schemas.LogoutResponse:
    """
    Logout a user by revoking their refresh token.
    
    Args:
        request: Logout request containing the refresh token to revoke
        database: Database dependency
        
    Returns:
        LogoutResponse with confirmation message
    """
    from services.api.database.refresh_token_db import revoke_refresh_token
    
    # Revoke the refresh token
    revoked = await revoke_refresh_token(database.session, request.refresh_token)
    
    if revoked:
        logger.info("User logged out successfully")
        return schemas.LogoutResponse(message="Logged out successfully")
    else:
        # Token not found - might have already been revoked or never existed
        # Return success anyway (idempotent operation)
        return schemas.LogoutResponse(message="Already logged out or token not found")


@router.post("/logout-all")
async def logout_all_devices(
    current_user: ValidateTokenResponse = Depends(get_current_user),
    database: Database = Depends(get_db),
) -> schemas.LogoutResponse:
    """
    Logout from all devices by revoking all refresh tokens for the user.
    
    Requires authentication via access token.
    
    Args:
        current_user: Current authenticated user
        database: Database dependency
        
    Returns:
        LogoutResponse with confirmation message
    """
    from services.api.database.refresh_token_db import revoke_user_tokens
    
    # Revoke all refresh tokens for the user
    count = await revoke_user_tokens(database.session, current_user.user_id)
    
    logger.info(f"User {current_user.user_id} logged out from all devices ({count} tokens revoked)")
    
    return schemas.LogoutResponse(
        message=f"Logged out from all devices ({count} active sessions revoked)"
    )
