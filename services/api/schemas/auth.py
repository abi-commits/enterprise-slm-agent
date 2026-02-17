"""Auth-related Pydantic schemas.

Schemas for login, token validation, and user management.
"""

from typing import Optional

from pydantic import BaseModel, Field

from core.models.user import UserRole


class LoginRequest(BaseModel):
    """Login request schema."""

    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")


class LoginResponse(BaseModel):
    """Login response schema."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    user_id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    role: str = Field(..., description="User role")


class ValidateTokenRequest(BaseModel):
    """Token validation request schema."""

    token: str = Field(..., description="JWT token to validate")


class ValidateTokenResponse(BaseModel):
    """Token validation response schema."""

    valid: bool = Field(..., description="Whether token is valid")
    user_id: Optional[str] = Field(None, description="User ID if valid")
    username: Optional[str] = Field(None, description="Username if valid")
    role: Optional[str] = Field(None, description="User role if valid")


class UserResponse(BaseModel):
    """User response schema."""

    id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    username: str = Field(..., description="Username")
    full_name: Optional[str] = Field(None, description="Full name")
    role: str = Field(..., description="User role")
    is_active: bool = Field(..., description="Whether user is active")


class CreateUserRequest(BaseModel):
    """Create user request schema."""

    email: str = Field(..., description="User email")
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    password: str = Field(..., min_length=8, max_length=100, description="Password")
    full_name: Optional[str] = Field(None, description="Full name")
    role: UserRole = Field(UserRole.OPERATIONS, description="User role")
