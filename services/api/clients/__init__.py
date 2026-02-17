"""HTTP clients for calling external services.

Re-exports all client symbols so existing imports like
`from services.api.clients import ServiceClientFactory, service_clients`
continue to work.
"""

from services.api.clients.circuit_breaker import CircuitBreaker, CircuitState
from services.api.clients.service_client import (
    ServiceClient,
    ServiceClientFactory,
    service_clients,
)

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "ServiceClient",
    "ServiceClientFactory",
    "service_clients",
]
