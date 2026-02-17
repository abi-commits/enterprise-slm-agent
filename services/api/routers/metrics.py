"""Metrics and Audit router for the consolidated API Service.

Merges:
- services/metrics/routers/metrics.py (metric recording and summary)
- services/metrics/routers/audit.py (audit log endpoints)

Endpoints:
- POST /metrics - Record metric data
- GET /metrics/summary - Get metrics summary
- GET /audit-log - Get paginated audit logs
- GET /audit-log/{log_id} - Get specific audit log entry
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from prometheus_client import make_asgi_app
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.database import (
    AuditLog,
    count_audit_logs,
    get_db_session,
    MetricRecord,
    query_audit_logs,
    store_audit_log,
    store_metric,
)
from services.api.schemas import (
    AuditLogEntry,
    AuditLogFilter,
    AuditLogResponse,
    MetricRequest,
    MetricResponse,
    MetricsSummary,
)
from services.api import prometheus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])

# Separate router for audit-log endpoints (different URL prefix)
audit_router = APIRouter(prefix="/audit-log", tags=["audit"])

# Create Prometheus ASGI app for mounting at /metrics/prometheus
prometheus_app = make_asgi_app()


# =============================================================================
# Metrics Endpoints
# =============================================================================


@router.post("", response_model=MetricResponse, status_code=status.HTTP_201_CREATED)
async def create_metric(
    metric: MetricRequest,
    db: AsyncSession = Depends(get_db_session),
) -> MetricResponse:
    """
    Record metric data.

    This endpoint accepts metrics data, stores it in PostgreSQL for
    audit purposes, and updates Prometheus metrics for real-time monitoring.
    """
    try:
        # Store metric in PostgreSQL
        stored_metric = await store_metric(
            session=db,
            user_id=metric.user_id,
            query=metric.query,
            query_confidence=metric.query_confidence,
            branch_taken=metric.branch_taken,
            escalation_flag=metric.escalation_flag,
            latency_per_service=metric.latency_per_service,
            token_usage=metric.token_usage,
            response_time_ms=metric.response_time_ms,
        )

        # Update Prometheus counters
        prometheus.update_metrics_on_request(
            user_id=metric.user_id,
            branch_taken=metric.branch_taken,
            response_time_ms_val=metric.response_time_ms,
        )

        # Update query confidence gauge
        prometheus.update_query_confidence(
            user_id=metric.user_id, confidence=metric.query_confidence
        )

        # If escalated to LLM, update escalation counter
        if metric.escalation_flag:
            reason = "low_confidence" if metric.query_confidence < 0.6 else "complex_query"
            prometheus.update_llm_escalation(user_id=metric.user_id, reason=reason)

        # Update latency per service if available
        if metric.latency_per_service:
            for service, latency_ms in metric.latency_per_service.items():
                latency_seconds = latency_ms / 1000.0
                prometheus.update_service_latency(service=service, latency_seconds=latency_seconds)

        # Update token usage if available (LLM was used)
        if metric.token_usage:
            for model_type, tokens in metric.token_usage.items():
                prometheus.update_token_usage(model_type=model_type, tokens=tokens)

        # Store audit log entry
        await store_audit_log(
            session=db,
            user_id=metric.user_id,
            action="metric_recorded",
            resource_type="query",
            details={
                "query": metric.query,
                "query_confidence": metric.query_confidence,
                "branch_taken": metric.branch_taken,
                "escalation_flag": metric.escalation_flag,
                "response_time_ms": metric.response_time_ms,
            },
        )

        logger.info(
            f"Metric recorded: user={metric.user_id}, "
            f"confidence={metric.query_confidence}, "
            f"branch={metric.branch_taken}, "
            f"escalated={metric.escalation_flag}"
        )

        return MetricResponse(
            success=True,
            message="Metric recorded successfully",
            metric_id=stored_metric.id,
        )

    except Exception as e:
        logger.error(f"Error recording metric: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record metric: {str(e)}",
        )


@router.get("/summary", status_code=status.HTTP_200_OK)
async def get_metrics_summary(db: AsyncSession = Depends(get_db_session)) -> dict:
    """
    Get summary of key metrics.

    Returns aggregated metrics including:
    - Total requests
    - LLM escalation rate
    - Average response time
    - Active users count
    - Cost metrics
    """
    try:
        # Get values from Prometheus gauges
        active_users_count = prometheus.active_users._value.get()
        cost_accumulated = prometheus.cost_accumulated_usd._value.get()
        cost_saved = prometheus.cost_saved_vs_llm_only._value.get()
        escalation_rate_value = prometheus.escalation_rate._value.get()

        return {
            "active_users": active_users_count,
            "cost_accumulated_usd": cost_accumulated,
            "cost_saved_vs_llm": cost_saved,
            "escalation_rate": escalation_rate_value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting metrics summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get metrics summary: {str(e)}",
        )


# =============================================================================
# Audit Log Endpoints (on audit_router with /audit-log prefix)
# =============================================================================


@audit_router.get("", response_model=AuditLogResponse, status_code=status.HTTP_200_OK)
async def get_audit_logs(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db_session),
) -> AuditLogResponse:
    """
    Get paginated audit logs with optional filters.

    Returns a list of audit log entries that can be filtered by:
    - user_id: Filter by specific user
    - action: Filter by action type (e.g., 'metric_recorded', 'login')
    - resource_type: Filter by resource type (e.g., 'query', 'document')
    - start_date: Filter by start date
    - end_date: Filter by end date
    - page: Page number (default: 1)
    - page_size: Items per page (default: 50, max: 100)
    """
    try:
        # Calculate offset
        offset = (page - 1) * page_size

        # Query audit logs
        logs = await query_audit_logs(
            session=db,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            start_date=start_date,
            end_date=end_date,
            limit=page_size,
            offset=offset,
        )

        # Get total count
        total = await count_audit_logs(
            session=db,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            start_date=start_date,
            end_date=end_date,
        )

        # Calculate total pages
        pages = (total + page_size - 1) // page_size if total > 0 else 1

        # Convert to response schema
        log_entries = [
            AuditLogEntry(
                id=log.id,
                user_id=log.user_id,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                details=log.details,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                timestamp=log.timestamp,
            )
            for log in logs
        ]

        return AuditLogResponse(
            logs=log_entries,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit logs: {str(e)}",
        )


@audit_router.get("/{log_id}", response_model=AuditLogEntry, status_code=status.HTTP_200_OK)
async def get_audit_log(
    log_id: int,
    db: AsyncSession = Depends(get_db_session),
) -> AuditLogEntry:
    """
    Get a specific audit log entry by ID.
    """
    try:
        logs = await query_audit_logs(
            session=db,
            limit=1,
            offset=log_id - 1,  # Approximate - should use ID-based query
        )

        if not logs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Audit log with ID {log_id} not found",
            )

        log = logs[0]
        return AuditLogEntry(
            id=log.id,
            user_id=log.user_id,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            details=log.details,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            timestamp=log.timestamp,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving audit log {log_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit log: {str(e)}",
        )
