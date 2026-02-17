"""JWT token creation and verification using python-jose."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from pydantic import BaseModel

from core.config.settings import get_settings

settings = get_settings()


class TokenData(BaseModel):
    """Token payload data."""

    sub: str  # User ID
    role: str  # User role
    exp: Optional[datetime] = None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: The data to encode in the token (should include user_id and role)
        expires_delta: Optional custom expiration time

    Returns:
        The encoded JWT token as a string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """
    Verify and decode a JWT token.

    Args:
        token: The JWT token string to verify

    Returns:
        TokenData if valid, None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )

        sub: Optional[str] = payload.get("sub")
        role: Optional[str] = payload.get("role")

        if sub is None or role is None:
            return None

        return TokenData(sub=sub, role=role)
    except JWTError:
        return None


def decode_token(token: str) -> Optional[dict]:
    """
    Decode a JWT token without verification (for debugging).

    Args:
        token: The JWT token string to decode

    Returns:
        The decoded payload dict if valid, None otherwise
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_signature": False},
        )
        return payload
    except JWTError:
        return None
