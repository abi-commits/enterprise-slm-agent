"""Pydantic schemas for the consolidated API Service.

Re-exports all schemas from submodules so existing imports like
`from services.api.schemas import LoginRequest` continue to work.
"""

from services.api.schemas.auth import (
    CreateUserRequest,
    LoginRequest,
    LoginResponse,
    UserResponse,
    ValidateTokenRequest,
    ValidateTokenResponse,
)
from services.api.schemas.metrics import (
    AuditLogEntry,
    AuditLogFilter,
    AuditLogResponse,
    MetricRequest,
    MetricResponse,
    MetricsSummary,
)
from services.api.schemas.query import (
    ClarificationOption,
    ClarificationRequest,
    ClarificationResponse,
    QueryRequest,
    QueryResponse,
    Source,
)

__all__ = [
    # Auth schemas
    "CreateUserRequest",
    "LoginRequest",
    "LoginResponse",
    "UserResponse",
    "ValidateTokenRequest",
    "ValidateTokenResponse",
    # Query schemas
    "ClarificationOption",
    "ClarificationRequest",
    "ClarificationResponse",
    "QueryRequest",
    "QueryResponse",
    "Source",
    # Metrics schemas
    "AuditLogEntry",
    "AuditLogFilter",
    "AuditLogResponse",
    "MetricRequest",
    "MetricResponse",
    "MetricsSummary",
]
