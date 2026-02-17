"""User models for authentication and authorization."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserRole(str, Enum):
    """User roles for RBAC."""

    ADMIN = "Admin"
    HR = "HR"
    ENGINEERING = "Engineering"
    FINANCE = "Finance"
    OPERATIONS = "Operations"


class UserBase(BaseModel):
    """Base user model with common fields."""

    email: EmailStr = Field(..., description="User email address")
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    full_name: Optional[str] = Field(None, description="User full name")
    role: UserRole = Field(UserRole.OPERATIONS, description="User role")


class UserCreate(UserBase):
    """Model for creating a new user."""

    password: str = Field(..., min_length=8, max_length=100, description="User password")


class UserInDB(BaseModel):
    """User model as stored in the database."""

    id: str = Field(..., description="User UUID")
    email: EmailStr = Field(..., description="User email address")
    username: str = Field(..., description="Username")
    hashed_password: str = Field(..., description="Hashed password")
    full_name: Optional[str] = Field(None, description="User full name")
    role: UserRole = Field(UserRole.OPERATIONS, description="User role")
    is_active: bool = Field(True, description="Whether user is active")
    created_at: datetime = Field(..., description="User creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class User(UserBase):
    """Public user model (excludes sensitive data)."""

    id: str = Field(..., description="User UUID")
    is_active: bool = Field(True, description="Whether user is active")
    created_at: datetime = Field(..., description="User creation timestamp")

    model_config = {"from_attributes": True}


class Token(BaseModel):
    """Token response model."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")


class TokenData(BaseModel):
    """Token payload data model."""

    user_id: Optional[str] = Field(None, description="User ID from token")
    username: Optional[str] = Field(None, description="Username from token")
    role: Optional[UserRole] = Field(None, description="User role from token")


class LoginRequest(BaseModel):
    """Login request model."""

    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")


class ValidateTokenRequest(BaseModel):
    """Token validation request model."""

    token: str = Field(..., description="JWT token to validate")
