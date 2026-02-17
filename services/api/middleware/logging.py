"""Request logging middleware.

Logs all incoming HTTP requests with method, path, status code,
and processing duration.
"""

import logging
import time

from fastapi import Request

logger = logging.getLogger(__name__)


async def log_requests(request: Request, call_next):
    """Log all incoming requests with timing."""
    start_time = time.time()

    # Process request
    response = await call_next(request)

    # Log request details
    process_time = (time.time() - start_time) * 1000
    logger.info(
        f"{request.method} {request.url.path} "
        f"status={response.status_code} "
        f"duration={process_time:.2f}ms"
    )

    return response
