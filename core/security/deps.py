"""FastAPI dependencies for authentication and authorization."""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from core.security.jwt import TokenData, verify_token

# OAuth2 scheme for extracting token from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    """
    Get the current authenticated user from the JWT token.

    Args:
        token: JWT token from Authorization header

    Returns:
        TokenData containing user_id and role

    Raises:
        HTTPException: If token is invalid or expired
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = verify_token(token)

    if token_data is None:
        raise credentials_exception

    return token_data


async def get_current_active_user(
    current_user: TokenData = Depends(get_current_user),
) -> TokenData:
    """
    Get the current active user.

    Args:
        current_user: Current user from token verification

    Returns:
        TokenData if user is active

    Raises:
        HTTPException: If user is inactive (can be extended for user status)
    """
    # For now, all users with valid tokens are active
    # This can be extended to check user status in the database
    return current_user


class RoleChecker:
    """Dependency for role-based access control."""

    def __init__(self, allowed_roles: list[str]):
        """
        Initialize RoleChecker.

        Args:
            allowed_roles: List of roles that are allowed to access the endpoint
        """
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: TokenData = Depends(get_current_user)) -> TokenData:
        """
        Check if the current user has an allowed role.

        Args:
            current_user: Current user from token verification

        Returns:
            TokenData if user has allowed role

        Raises:
            HTTPException: If user role is not allowed
        """
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not authorized to access this resource",
            )
        return current_user


# Pre-defined role checkers for common roles
require_admin = RoleChecker(["Admin"])
require_hr = RoleChecker(["Admin", "HR"])
require_engineering = RoleChecker(["Admin", "Engineering"])
require_finance = RoleChecker(["Admin", "Finance"])
require_operations = RoleChecker(["Admin", "Operations"])
require_any_role = RoleChecker(["Admin", "HR", "Engineering", "Finance", "Operations"])
