"""Authentication router for the consolidated API Service.

Merges:
- services/auth/routers/auth.py (login endpoint)
- services/auth/routers/validate.py (token validation endpoint)

Fixes:
- Added missing Depends import that was absent in the original validate.py
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from core.config.settings import get_settings
from core.security.jwt import create_access_token, verify_token, TokenData
from core.security.password import verify_password
from services.api.database import Database, db, get_db
from services.api.schemas import (
    LoginRequest,
    LoginResponse,
    ValidateTokenRequest,
    ValidateTokenResponse,
)
from services.api import prometheus

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

    return LoginResponse(
        access_token=access_token,
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
