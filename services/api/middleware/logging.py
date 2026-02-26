"""Request logging middleware.

Logs all incoming HTTP requests with structured data:
- Method, path, status code, duration
- Request/response size
- User ID (from auth token)
- Request ID (for distributed tracing)
- Client IP and user agent
- Trace ID (for OpenTelemetry correlation)
"""

import time
import uuid
from typing import Optional

from fastapi import Request
from opentelemetry import trace
import structlog

logger = structlog.get_logger(__name__)


async def log_requests(request: Request, call_next):
    """Log all incoming requests with timing and context."""
    # Get or generate request ID for tracing
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    
    # Get trace ID from OpenTelemetry span context
    span = trace.get_current_span()
    trace_id = trace.format_trace_id(span.get_span_context().trace_id)
    
    start_time = time.time()
    
    # Extract user ID from token if available
    user_id = None
    try:
        from services.api.routers.auth import oauth2_scheme
        # Try to get token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            from core.security.jwt import verify_token
            token_data = verify_token(token)
            if token_data:
                user_id = token_data.sub
    except Exception:
        pass  # Token verification optional for logging
    
    # Get client IP (handle proxies)
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"
    
    user_agent = request.headers.get("User-Agent", "unknown")
    
    # Bind request context to logger
    logger = logger.bind(
        request_id=request_id,
        trace_id=trace_id,
        method=request.method,
        path=request.url.path,
        query_params=dict(request.query_params) if request.query_params else None,
        client_ip=client_ip,
        user_agent=user_agent,
        user_id=user_id,
    )
    
    logger.debug("request_received")
    
    # Process request
    response = await call_next(request)
    
    # Calculate timing
    process_time_ms = (time.time() - start_time) * 1000
    
    # Log request completion
    logger.info(
        "request_completed",
        status_code=response.status_code,
        duration_ms=round(process_time_ms, 2),
    )

    return response
