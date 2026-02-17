"""Database module for the consolidated API Service.

Unified database layer using SQLAlchemy async for all operations:
- User authentication (auth_db)
- Metrics and audit logging (metrics_db)

Uses a shared connection pool via DatabaseManager for efficient
resource utilization.
"""

from services.api.database.auth_db import Database, db, get_db
from services.api.database.metrics_db import (
    close_db,
    count_audit_logs,
    engine,
    get_db_session,
    init_db,
    query_audit_logs,
    store_audit_log,
    store_metric,
)
from services.api.database.models import AuditLog, Base, MetricRecord, User
from services.api.database.session import DatabaseManager, db_manager

__all__ = [
    # Models
    "AuditLog",
    "Base",
    "MetricRecord",
    "User",
    # Session management
    "DatabaseManager",
    "db_manager",
    # Auth DB
    "Database",
    "db",
    "get_db",
    # Metrics DB
    "close_db",
    "count_audit_logs",
    "engine",
    "get_db_session",
    "init_db",
    "query_audit_logs",
    "store_audit_log",
    "store_metric",
]
