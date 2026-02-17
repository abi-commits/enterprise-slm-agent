"""Middleware for the consolidated API Service.

Re-exports all middleware functions so they can be imported from
`services.api.middleware` directly.
"""

from services.api.middleware.logging import log_requests
from services.api.middleware.rate_limit import (
    close_rate_limit_redis,
    connect_rate_limit_redis,
    get_rate_limit_redis,
    rate_limit_middleware,
)

__all__ = [
    "close_rate_limit_redis",
    "connect_rate_limit_redis",
    "get_rate_limit_redis",
    "log_requests",
    "rate_limit_middleware",
]
