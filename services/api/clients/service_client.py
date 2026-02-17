"""HTTP client for calling external Knowledge and Inference services.

Simplified from services/gateway/service_client.py. Only maintains clients for
the two remaining external service dependencies:
- Knowledge Service (search, document retrieval)
- Inference Service (query optimization, answer generation)

Auth and Metrics are now in-process and do not require HTTP clients.

Features:
- Circuit breaker for cascading failure protection
- Retry with exponential backoff for transient failures
- Request ID propagation for distributed tracing
"""

import asyncio
import logging
import random
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from core.config.settings import get_settings
from services.api.clients.circuit_breaker import CircuitBreaker, CircuitState

logger = logging.getLogger(__name__)

settings = get_settings()

# Context variable for request ID propagation across async calls
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    
    max_retries: int = 3
    base_delay: float = 0.5  # Base delay in seconds
    max_delay: float = 30.0  # Maximum delay in seconds
    exponential_base: float = 2.0  # Exponential backoff multiplier
    jitter: bool = True  # Add randomness to prevent thundering herd
    
    # HTTP status codes that should trigger a retry
    retryable_status_codes: tuple[int, ...] = (
        408,  # Request Timeout
        429,  # Too Many Requests
        500,  # Internal Server Error
        502,  # Bad Gateway
        503,  # Service Unavailable
        504,  # Gateway Timeout
    )


def get_current_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return request_id_var.get()


def set_current_request_id(request_id: str) -> None:
    """Set the current request ID in context."""
    request_id_var.set(request_id)


def clear_current_request_id() -> None:
    """Clear the current request ID from context."""
    request_id_var.set(None)


def calculate_backoff_delay(
    attempt: int,
    config: RetryConfig,
) -> float:
    """Calculate the delay before the next retry attempt.
    
    Uses exponential backoff with optional jitter to prevent
    thundering herd problems.
    
    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration
        
    Returns:
        Delay in seconds before next retry
    """
    delay = config.base_delay * (config.exponential_base ** attempt)
    delay = min(delay, config.max_delay)
    
    if config.jitter:
        # Add up to 25% jitter
        jitter_amount = delay * 0.25 * random.random()
        delay += jitter_amount
    
    return delay


class ServiceClient:
    """HTTP client for calling downstream services with retry and circuit breaker.
    
    Features:
    - Retry with exponential backoff for transient failures
    - Circuit breaker to prevent cascading failures
    - Request ID propagation for distributed tracing
    """

    def __init__(
        self,
        base_url: str,
        service_name: str,
        timeout: float = 30.0,
        retry_config: Optional[RetryConfig] = None,
    ):
        """
        Initialize the service client.

        Args:
            base_url: Base URL for the service
            service_name: Name of the service for logging
            timeout: Request timeout in seconds
            retry_config: Configuration for retry behavior
        """
        self.base_url = base_url
        self.service_name = service_name
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig()
        self.circuit_breaker = CircuitBreaker()
        self._client: Optional[httpx.AsyncClient] = None

    def _get_headers(self, headers: Optional[dict[str, str]] = None) -> dict[str, str]:
        """Build headers with request ID propagation."""
        result = headers.copy() if headers else {}
        request_id = get_current_request_id()
        if request_id:
            result["X-Request-ID"] = request_id
        return result

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"X-Request-ID": get_current_request_id() or ""},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error should trigger a retry.
        
        Args:
            error: The exception that occurred
            
        Returns:
            True if the request should be retried
        """
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code in self.retry_config.retryable_status_codes
        
        # Retry connection and timeout errors
        if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)):
            return True
        
        return False

    async def _execute_with_retry(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> Optional[dict[str, Any]]:
        """Execute an HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments for the request
            
        Returns:
            Response JSON data or None if all retries failed
        """
        if not self.circuit_breaker.can_execute():
            logger.warning(
                f"Circuit breaker open for {self.service_name}, skipping request"
            )
            return None
        
        last_error: Optional[Exception] = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                client = await self.get_client()
                request_headers = self._get_headers(kwargs.pop("headers", None))
                
                if method.upper() == "POST":
                    response = await client.post(
                        endpoint, 
                        json=kwargs.get("data"), 
                        headers=request_headers,
                    )
                elif method.upper() == "GET":
                    response = await client.get(
                        endpoint,
                        params=kwargs.get("params"),
                        headers=request_headers,
                    )
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                response.raise_for_status()
                
                # Success - record and return
                if self.circuit_breaker.state == CircuitState.HALF_OPEN:
                    self.circuit_breaker.half_open_calls += 1
                self.circuit_breaker.record_success()
                
                return response.json()
                
            except Exception as e:
                last_error = e
                
                # Check if we should retry
                if attempt < self.retry_config.max_retries and self._is_retryable_error(e):
                    delay = calculate_backoff_delay(attempt, self.retry_config)
                    logger.warning(
                        f"Retrying {self.service_name} {method} {endpoint} "
                        f"(attempt {attempt + 1}/{self.retry_config.max_retries + 1}) "
                        f"after {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                
                # Not retryable or no more retries
                break
        
        # All retries exhausted, record failure
        if isinstance(last_error, httpx.HTTPStatusError):
            logger.error(
                f"HTTP error calling {self.service_name}: {last_error.response.status_code} "
                f"after {self.retry_config.max_retries + 1} attempts"
            )
        elif isinstance(last_error, httpx.RequestError):
            logger.error(
                f"Request error calling {self.service_name}: {last_error} "
                f"after {self.retry_config.max_retries + 1} attempts"
            )
        else:
            logger.error(
                f"Unexpected error calling {self.service_name}: {last_error} "
                f"after {self.retry_config.max_retries + 1} attempts"
            )
        
        self.circuit_breaker.record_failure()
        return None

    async def post(
        self,
        endpoint: str,
        data: dict[str, Any],
        headers: Optional[dict[str, str]] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Make a POST request to the service with retry.

        Args:
            endpoint: API endpoint path
            data: Request body data
            headers: Optional request headers

        Returns:
            Response JSON data or None if failed
        """
        return await self._execute_with_retry(
            method="POST",
            endpoint=endpoint,
            data=data,
            headers=headers,
        )

    async def get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Make a GET request to the service with retry.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            headers: Optional request headers

        Returns:
            Response JSON data or None if failed
        """
        return await self._execute_with_retry(
            method="GET",
            endpoint=endpoint,
            params=params,
            headers=headers,
        )


class ServiceClientFactory:
    """Factory for creating service clients for external services only.

    Only Knowledge and Inference services require HTTP clients.
    Auth and Metrics are now handled in-process within this API service.
    """

    def __init__(self):
        """Initialize the factory."""
        self._clients: dict[str, ServiceClient] = {}

    def get_knowledge_client(self) -> ServiceClient:
        """Get or create the Knowledge service client."""
        if "knowledge" not in self._clients:
            knowledge_url = getattr(
                settings, "knowledge_service_url", "http://knowledge-service:8000"
            )
            self._clients["knowledge"] = ServiceClient(
                base_url=knowledge_url,
                service_name="knowledge",
                timeout=15.0,
            )
        return self._clients["knowledge"]

    def get_inference_client(self) -> ServiceClient:
        """Get or create the Inference service client."""
        if "inference" not in self._clients:
            inference_url = getattr(
                settings, "inference_service_url", "http://inference-service:8000"
            )
            self._clients["inference"] = ServiceClient(
                base_url=inference_url,
                service_name="inference",
                timeout=60.0,
            )
        return self._clients["inference"]

    async def close_all(self) -> None:
        """Close all service clients."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()


# Global service client factory
service_clients = ServiceClientFactory()
