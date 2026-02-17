"""Core security module."""

from core.security.deps import (
    RoleChecker,
    get_current_active_user,
    get_current_user,
    require_admin,
    require_any_role,
    require_engineering,
    require_finance,
    require_hr,
    require_operations,
)
from core.security.jwt import TokenData, create_access_token, decode_token, verify_token
from core.security.password import get_password_hash, verify_password

__all__ = [
    # Password
    "verify_password",
    "get_password_hash",
    # JWT
    "create_access_token",
    "verify_token",
    "decode_token",
    "TokenData",
    # Dependencies
    "get_current_user",
    "get_current_active_user",
    "RoleChecker",
    "require_admin",
    "require_hr",
    "require_engineering",
    "require_finance",
    "require_operations",
    "require_any_role",
]
