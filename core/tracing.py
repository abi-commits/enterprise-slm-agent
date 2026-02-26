"""OpenTelemetry distributed tracing configuration.

Enables distributed tracing across all microservices to track requests
through the entire system. Works with Jaeger, Zipkin, or OTLP backends.

Provides:
- Automatic request tracing with unique trace IDs
- Request correlation across service boundaries
- Span creation for service calls, database operations, etc.
- Context propagation via HTTP headers (W3C Trace Context)
"""

import logging
from typing import Optional

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.propagate import set_global_textmap

logger = logging.getLogger(__name__)


def configure_tracing(
    service_name: str,
    otlp_endpoint: Optional[str] = None,
    environment: str = "development",
    enabled: bool = True,
):
    """
    Configure OpenTelemetry distributed tracing.
    
    Args:
        service_name: Name of the service (e.g., 'api-service')
        otlp_endpoint: OTLP gRPC exporter endpoint (e.g., 'http://localhost:4317')
                      If None, traces are not exported but still collected locally
        environment: Environment name (development, staging, production)
        enabled: Whether to enable tracing (can disable for testing)
        
    Returns:
        Configured TracerProvider instance
    """
    if not enabled:
        logger.info("Tracing disabled")
        return trace.get_tracer_provider()
    
    # Create resource with service metadata
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
        "deployment.environment": environment,
    })
    
    # Create tracer provider
    tracer_provider = TracerProvider(resource=resource)
    
    # Configure OTLP exporter if endpoint provided
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(
                "OTLP span exporter configured",
                extra={"endpoint": otlp_endpoint, "service": service_name},
            )
        except ImportError:
            logger.warning(
                "OpenTelemetry OTLP exporter not installed. "
                "Install: pip install opentelemetry-exporter-otlp"
            )
        except Exception as e:
            logger.warning(f"Failed to configure OTLP exporter: {e}")
    else:
        logger.info("No OTLP endpoint configured - traces will be collected locally only")
    
    # Set global tracer provider
    trace.set_tracer_provider(tracer_provider)
    
    logger.info(
        "Tracing configured",
        extra={"service": service_name, "environment": environment},
    )
    
    return tracer_provider


def instrument_fastapi(app) -> None:
    """
    Instrument FastAPI application for automatic tracing.
    
    Automatically creates spans for:
    - HTTP requests (method, path, status)
    - Request duration
    - Request headers and query parameters
    
    Args:
        app: FastAPI application instance
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumented for tracing")
    except ImportError:
        logger.warning(
            "OpenTelemetry FastAPI instrumentation not installed. "
            "Install: pip install opentelemetry-instrumentation-fastapi"
        )
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI: {e}")


def instrument_http_clients() -> None:
    """
    Instrument HTTP clients for automatic request tracing.
    
    Traces all outgoing HTTP requests (httpx, requests).
    Automatically propagates trace context to downstream services.
    """
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        
        HTTPXClientInstrumentor().instrument()
        logger.info("HTTPX client instrumented for tracing")
    except ImportError:
        logger.warning(
            "OpenTelemetry HTTPX instrumentation not installed. "
            "Install: pip install opentelemetry-instrumentation-httpx"
        )
    except Exception as e:
        logger.warning(f"Failed to instrument HTTPX: {e}")
    
    try:
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        
        RequestsInstrumentor().instrument()
        logger.info("Requests library instrumented for tracing")
    except ImportError:
        logger.warning(
            "OpenTelemetry Requests instrumentation not installed. "
            "Install: pip install opentelemetry-instrumentation-requests"
        )
    except Exception as e:
        logger.warning(f"Failed to instrument requests: {e}")


def instrument_database() -> None:
    """
    Instrument database operations for tracing.
    
    Traces all SQLAlchemy queries with:
    - SQL statement
    - Query duration
    - Database info
    """
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        
        SQLAlchemyInstrumentor().instrument()
        logger.info("SQLAlchemy instrumented for tracing")
    except ImportError:
        logger.warning(
            "OpenTelemetry SQLAlchemy instrumentation not installed. "
            "Install: pip install opentelemetry-instrumentation-sqlalchemy"
        )
    except Exception as e:
        logger.warning(f"Failed to instrument SQLAlchemy: {e}")


def instrument_cache() -> None:
    """
    Instrument Redis cache operations for tracing.
    
    Traces all Redis calls with:
    - Command name
    - Key information
    - Execution duration
    """
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        
        RedisInstrumentor().instrument()
        logger.info("Redis instrumented for tracing")
    except ImportError:
        logger.warning(
            "OpenTelemetry Redis instrumentation not installed. "
            "Install: pip install opentelemetry-instrumentation-redis"
        )
    except Exception as e:
        logger.warning(f"Failed to instrument Redis: {e}")


def get_tracer(name: str = __name__) -> trace.Tracer:
    """
    Get a tracer instance for the calling module.
    
    Args:
        name: Logger/tracer name (typically __name__)
        
    Returns:
        Configured tracer instance
    """
    return trace.get_tracer(name)


def create_span(name: str, attributes: Optional[dict] = None):
    """
    Create and return a context manager for a span.
    
    Usage:
        with create_span("database_query", {"query_type": "select"}):
            # Your code here - span will be recorded
            
    Args:
        name: Span name
        attributes: Additional attributes to attach to span
        
    Returns:
        Context manager for the span
    """
    tracer = get_tracer()
    span = tracer.start_span(name)
    
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
    
    class SpanContextManager:
        def __enter__(self):
            return span
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type:
                span.set_attribute("error", True)
                span.set_attribute("error.type", exc_type.__name__)
                if exc_val:
                    span.set_attribute("error.message", str(exc_val))
            span.end()
    
    return SpanContextManager()


def add_span_attribute(key: str, value) -> None:
    """
    Add an attribute to the current active span.
    
    Args:
        key: Attribute key
        value: Attribute value
    """
    span = trace.get_current_span()
    if span:
        span.set_attribute(key, value)


def record_span_event(name: str, attributes: Optional[dict] = None) -> None:
    """
    Record an event on the current active span.
    
    Args:
        name: Event name
        attributes: Event attributes
    """
    span = trace.get_current_span()
    if span:
        span.add_event(name, attributes or {})
