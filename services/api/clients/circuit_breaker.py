"""Circuit breaker pattern for service calls.

Implements a circuit breaker with three states (CLOSED, OPEN, HALF_OPEN)
to protect against cascading failures when calling external services.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Circuit breaker for service calls."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3

    state: CircuitState = field(default=CircuitState.CLOSED)
    failure_count: int = field(default=0)
    success_count: int = field(default=0)
    last_failure_time: float = field(default=0)
    half_open_calls: int = field(default=0)

    def record_success(self) -> None:
        """Record a successful call."""
        self.failure_count = 0
        self.success_count += 1
        if self.state == CircuitState.HALF_OPEN:
            if self.success_count >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.success_count = 0
                logger.info("Circuit breaker closed")

    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker opened after half-open failure")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker opened after failure threshold")

    def can_execute(self) -> bool:
        """Check if a call can be executed."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.success_count = 0
                logger.info("Circuit breaker half-open")
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False

        return False
