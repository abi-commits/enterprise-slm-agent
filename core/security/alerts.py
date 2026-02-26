"""Security alerting and incident response.

Handles security events like token theft, suspicious activity, and breaches.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import insert
import structlog

from services.api.database.models import AuditLog
from services.api.database.session import db_manager

logger = structlog.get_logger(__name__)


class SecurityEventType(str, Enum):
    """Types of security events."""

    REFRESH_TOKEN_REUSE = "refresh_token_reuse"
    MULTIPLE_FAILED_LOGINS = "multiple_failed_logins"
    SUSPICIOUS_IP_CHANGE = "suspicious_ip_change"
    PRIVILEGE_ESCALATION = "privilege_escalation"


class SecurityEventSeverity(str, Enum):
    """Severity levels for security events."""

    CRITICAL = "critical"  # Confirmed breach, immediate action required
    HIGH = "high"          # Likely breach, investigate urgently
    MEDIUM = "medium"      # Suspicious activity, monitor
    LOW = "low"            # Anomalous but probably benign


class SecurityEvent(BaseModel):
    """Security event data."""

    event_type: SecurityEventType
    severity: SecurityEventSeverity
    user_id: str
    description: str
    metadata: dict
    timestamp: datetime


_SEVERITY_LOG_METHOD = {
    SecurityEventSeverity.CRITICAL: "critical",
    SecurityEventSeverity.HIGH: "error",
    SecurityEventSeverity.MEDIUM: "warning",
    SecurityEventSeverity.LOW: "info",
}


async def alert_security_team(
    event_type: SecurityEventType,
    user_id: str,
    severity: SecurityEventSeverity,
    description: str,
    metadata: Optional[dict] = None,
) -> None:
    """
    Alert the security team about a security event.

    In production, this should:
    - Send email to security@company.com
    - Post to Slack #security-alerts channel
    - Create PagerDuty incident (for CRITICAL)
    - Log to SIEM (Security Information and Event Management)
    - Create ticket in incident management system

    Args:
        event_type: Type of security event
        user_id: User ID involved in the event
        severity: Severity level
        description: Human-readable description
        metadata: Additional context (IP, timestamps, etc.)
    """
    event = SecurityEvent(
        event_type=event_type,
        severity=severity,
        user_id=user_id,
        description=description,
        metadata=metadata or {},
        timestamp=datetime.utcnow(),
    )

    log_method = getattr(logger, _SEVERITY_LOG_METHOD[severity])
    log_method(
        "security_event",
        event_type=event.event_type.value,
        user_id=event.user_id,
        severity=event.severity.value,
        description=event.description,
        metadata=event.metadata,
        timestamp=event.timestamp.isoformat(),
    )

    # Also persist to audit log for compliance and forensics
    try:
        await log_security_event_to_audit(
            user_id=user_id,
            event_type=event_type.value,
            details={
                "severity": severity.value,
                "description": description,
                **(metadata or {}),
            },
        )
    except Exception as audit_error:
        logger.error(
            "failed_to_write_security_audit_log",
            user_id=user_id,
            event_type=event_type.value,
            error=str(audit_error),
        )

    # TODO: Production integrations
    # if severity == SecurityEventSeverity.CRITICAL:
    #     await send_pagerduty_alert(event)
    #     await send_email_alert("security@company.com", event)
    #     await post_to_slack("#security-alerts-critical", event)
    # elif severity == SecurityEventSeverity.HIGH:
    #     await send_email_alert("security@company.com", event)
    #     await post_to_slack("#security-alerts", event)
    # else:
    #     await post_to_slack("#security-monitoring", event)

    # TODO: Log to SIEM
    # await send_to_siem(event)

    # TODO: Create incident ticket
    # if severity in [SecurityEventSeverity.CRITICAL, SecurityEventSeverity.HIGH]:
    #     await create_incident_ticket(event)


async def flag_user_for_password_reset(user_id: str, reason: str) -> None:
    """
    Flag a user account to require password reset on next login.

    This should:
    - Set a flag in the users table (requires_password_reset=True)
    - Send email to user explaining why
    - Optionally lock account until reset is complete

    Args:
        user_id: User ID to flag
        reason: Reason for password reset requirement
    """
    # TODO: Update user record
    # async with db_manager.session() as session:
    #     await session.execute(
    #         update(User)
    #         .where(User.id == user_id)
    #         .values(requires_password_reset=True, password_reset_reason=reason)
    #     )
    #     await session.commit()

    # TODO: Send email to user
    # await send_email(
    #     to=user_email,
    #     subject="Password reset required",
    #     body=f"Your account requires a password reset due to: {reason}"
    # )

    logger.warning(
        "user_flagged_for_password_reset",
        user_id=user_id,
        reason=reason,
    )


async def log_security_event_to_audit(
    user_id: str,
    event_type: str,
    details: dict,
    ip_address: Optional[str] = None,
) -> None:
    """
    Log security event to audit_logs table for compliance and forensics.

    Args:
        user_id: User ID involved
        event_type: Type of security event
        details: Event details
        ip_address: Optional originating IP address
    """
    async with db_manager.session() as session:
        await session.execute(
            insert(AuditLog).values(
                user_id=user_id,
                action=event_type,
                resource_type="security_event",
                details=details,
                ip_address=ip_address,
            )
        )
        await session.commit()

    logger.info(
        "security_audit_log_written",
        event_type=event_type,
        user_id=user_id,
        ip_address=ip_address,
    )