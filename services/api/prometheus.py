"""Prometheus metrics for the consolidated API Service.

Copied from services/metrics/prometheus.py. All Prometheus counters,
gauges, histograms and helper functions for tracking request metrics,
latency, token usage, escalation rates, and costs.
"""

from prometheus_client import Counter, Gauge, Histogram

# Counters
total_requests = Counter(
    "slm_total_requests",
    "Total number of requests processed",
    ["user_id", "branch_taken"],
)

llm_escalations = Counter(
    "slm_llm_escalations_total",
    "Total number of LLM escalations",
    ["user_id", "reason"],
)

auth_failures = Counter(
    "slm_auth_failures_total",
    "Total number of authentication failures",
    ["reason"],
)

# Histograms
query_latency_seconds = Histogram(
    "slm_query_latency_seconds",
    "Query latency in seconds",
    ["service"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

token_usage = Histogram(
    "slm_token_usage",
    "Token usage per request",
    ["model_type"],
    buckets=(10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000),
)

response_time_ms = Histogram(
    "slm_response_time_ms",
    "Total response time in milliseconds",
    buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
)

# Gauges
active_users = Gauge(
    "slm_active_users",
    "Number of active users in the current window",
)

cost_accumulated_usd = Gauge(
    "slm_cost_accumulated_usd",
    "Accumulated cost in USD",
)

query_confidence = Gauge(
    "slm_query_confidence",
    "Current query confidence score",
    ["user_id"],
)

# Additional metrics for tracking
escalation_rate = Gauge(
    "slm_escalation_rate",
    "Current escalation rate (percentage)",
)

avg_latency_per_service = Gauge(
    "slm_avg_latency_per_service_seconds",
    "Average latency per service in seconds",
    ["service"],
)

tokens_used_today = Gauge(
    "slm_tokens_used_today",
    "Total tokens used today",
    ["model_type"],
)

cost_saved_vs_llm_only = Gauge(
    "slm_cost_saved_vs_llm_only_usd",
    "Cost saved compared to LLM-only baseline",
)


def update_metrics_on_request(
    user_id: str,
    branch_taken: str,
    response_time_ms_val: float,
) -> None:
    """Update metrics when a request is processed."""
    total_requests.labels(user_id=user_id, branch_taken=branch_taken).inc()
    response_time_ms.observe(response_time_ms_val)


def update_llm_escalation(user_id: str, reason: str) -> None:
    """Update LLM escalation counter."""
    llm_escalations.labels(user_id=user_id, reason=reason).inc()


def update_token_usage(model_type: str, tokens: int) -> None:
    """Update token usage histogram."""
    token_usage.labels(model_type=model_type).observe(tokens)


def update_service_latency(service: str, latency_seconds: float) -> None:
    """Update service latency histogram."""
    query_latency_seconds.labels(service=service).observe(latency_seconds)


def update_active_users(count: int) -> None:
    """Update active users gauge."""
    active_users.set(count)


def update_accumulated_cost(cost_usd: float) -> None:
    """Update accumulated cost gauge."""
    cost_accumulated_usd.set(cost_usd)


def update_query_confidence(user_id: str, confidence: float) -> None:
    """Update query confidence gauge."""
    query_confidence.labels(user_id=user_id).set(confidence)


def update_escalation_rate(rate: float) -> None:
    """Update escalation rate gauge (0-100)."""
    escalation_rate.set(rate)


def update_avg_service_latency(service: str, latency_seconds: float) -> None:
    """Update average latency per service gauge."""
    avg_latency_per_service.labels(service=service).set(latency_seconds)


def update_tokens_used_today(model_type: str, tokens: int) -> None:
    """Update tokens used today gauge."""
    tokens_used_today.labels(model_type=model_type).set(tokens)


def update_cost_saved(cost_saved_usd: float) -> None:
    """Update cost saved compared to LLM-only baseline."""
    cost_saved_vs_llm_only.set(cost_saved_usd)


def record_auth_failure(reason: str) -> None:
    """Record an authentication failure."""
    auth_failures.labels(reason=reason).inc()
