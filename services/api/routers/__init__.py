"""Routers for the consolidated API Service."""

from .auth import router as auth_router
from .metrics import audit_router, router as metrics_router
from .query import router as query_router

__all__ = ["auth_router", "audit_router", "metrics_router", "query_router"]
