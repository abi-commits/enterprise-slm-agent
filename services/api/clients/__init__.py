"""HTTP clients for calling external services.

Re-exports all client symbols so existing imports like
`from services.api.clients import ServiceClientFactory, service_clients`
continue to work.
"""

from services.api.clients.circuit_breaker import CircuitBreaker, CircuitState
from services.api.clients.service_client import (
    ServiceClient,
    ServiceClientFactory,
    clear_current_request_id,
    get_current_request_id,
    service_clients,
    set_current_request_id,
)

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "ServiceClient",
    "ServiceClientFactory",
    "service_clients",
    "get_current_request_id",
    "set_current_request_id",
    "clear_current_request_id",
]
