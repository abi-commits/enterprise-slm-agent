"""Structured logging configuration using structlog.

Configures JSON logging for all services to enable:
- Structured log aggregation (ELK, Splunk, Loki, etc.)
- Easy tracing and correlation
- Automatic log parsing and analysis
"""

import logging
import logging.config
from typing import Any, Optional

import structlog


def configure_logging(
    log_level: str = "INFO",
    json_output: bool = True,
    service_name: str = "slm-service",
) -> None:
    """
    Configure structlog for JSON output.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: Whether to output JSON (True) or plain text (False)
        service_name: Service name for log context
    """
    # Convert log_level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Configure standard library logging to use structlog
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": structlog.dev.ConsoleRenderer(),
                    "foreign_pre_chain": [
                        structlog.stdlib.add_log_level,
                        structlog.stdlib.add_logger_name,
                    ],
                },
                "json": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": structlog.processors.JSONRenderer(),
                    "foreign_pre_chain": [
                        structlog.stdlib.add_log_level,
                        structlog.stdlib.add_logger_name,
                    ],
                },
            },
            "handlers": {
                "default": {
                    "level": numeric_level,
                    "class": "logging.StreamHandler",
                    "formatter": "json" if json_output else "plain",
                },
            },
            "loggers": {
                "": {
                    "handlers": ["default"],
                    "level": numeric_level,
                    "propagate": True,
                },
            },
        }
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            # Add log level and logger name
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            # Add timestamp
            structlog.processors.TimeStamper(fmt="iso"),
            # Add service name to all logs
            structlog.processors.dict_tracebacks,
            # Pass through standard library logging
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Get structlog logger and set up initial context
    logger = structlog.get_logger()
    
    # Log startup
    logger.info(
        "logging_configured",
        log_level=log_level,
        json_output=json_output,
        service_name=service_name,
    )


def get_logger(name: str = __name__) -> Any:
    """
    Get a structlog logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


def bind_request_context(
    request_id: str,
    user_id: Optional[str] = None,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Bind request-specific context to all subsequent logs.
    
    Use in middleware to automatically include this data in all logs
    for easier distributed tracing.
    
    Args:
        request_id: Unique request identifier
        user_id: User ID from auth token
        user_agent: Client user agent
        ip_address: Client IP address
    """
    logger = structlog.get_logger()
    
    context = {"request_id": request_id}
    if user_id:
        context["user_id"] = user_id
    if user_agent:
        context["user_agent"] = user_agent
    if ip_address:
        context["ip_address"] = ip_address
    
    logger.bind(**context)


def clear_request_context() -> None:
    """Clear request-specific context at end of request."""
    logger = structlog.get_logger()
    logger.unbind()
