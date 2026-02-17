"""Metrics/Audit database module using SQLAlchemy async.

Provides CRUD functions for storing and querying metrics and audit
log records using the unified SQLAlchemy async session pattern.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.database.models import AuditLog, Base, MetricRecord
from services.api.database.session import db_manager, get_db_session

# Re-export session utilities for backwards compatibility
engine = db_manager.engine


async def init_db() -> None:
    """Initialize the database tables."""
    await db_manager.connect()


async def close_db() -> None:
    """Close database connections."""
    await db_manager.disconnect()


async def store_metric(
    session: AsyncSession,
    user_id: str,
    query: str,
    query_confidence: float,
    branch_taken: str,
    escalation_flag: bool,
    latency_per_service: Optional[Dict[str, float]] = None,
    token_usage: Optional[Dict[str, int]] = None,
    response_time_ms: float = 0.0,
) -> MetricRecord:
    """Store a metric record."""
    metric = MetricRecord(
        user_id=user_id,
        query=query,
        query_confidence=query_confidence,
        branch_taken=branch_taken,
        escalation_flag=escalation_flag,
        latency_per_service=latency_per_service,
        token_usage=token_usage,
        response_time_ms=response_time_ms,
    )
    session.add(metric)
    await session.commit()
    await session.refresh(metric)
    return metric


async def store_audit_log(
    session: AsyncSession,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """Store an audit log entry."""
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(audit_log)
    await session.commit()
    await session.refresh(audit_log)
    return audit_log


async def query_audit_logs(
    session: AsyncSession,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[AuditLog]:
    """Query audit logs with filters."""
    query = select(AuditLog).order_by(AuditLog.timestamp.desc())

    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if start_date:
        query = query.where(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.where(AuditLog.timestamp <= end_date)

    query = query.limit(limit).offset(offset)

    result = await session.execute(query)
    return list(result.scalars().all())


async def count_audit_logs(
    session: AsyncSession,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> int:
    """Count audit logs with filters."""
    query = select(AuditLog)

    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if start_date:
        query = query.where(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.where(AuditLog.timestamp <= end_date)

    result = await session.execute(query)
    return len(list(result.scalars().all()))
