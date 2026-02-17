"""Rate limiting middleware using Redis.

Provides per-client rate limiting based on JWT token or IP address,
with configurable request limits and time windows.
"""

import hashlib
import logging

import redis.asyncio as redis
from fastapi import Request, status
from fastapi.responses import JSONResponse

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Redis client for rate limiting
_rate_limit_redis: redis.Redis = None

# Lua script for atomic rate limit check and increment
# Keys: [rate_limit_key]
# Args: [max_requests, window_seconds]
# Returns: current_count (after increment)
RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local max_requests = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local current = redis.call('GET', key)
if current == false then
    -- Key doesn't exist, set it with value 1 and expiration
    redis.call('SETEX', key, window, 1)
    return 1
end

local count = tonumber(current)
if count >= max_requests then
    -- Rate limit exceeded, return count without incrementing
    return count
else
    -- Increment and return new count
    return redis.call('INCR', key)
end
"""


async def get_rate_limit_redis() -> redis.Redis:
    """Get or create the Redis client for rate limiting."""
    global _rate_limit_redis
    if _rate_limit_redis is None:
        _rate_limit_redis = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _rate_limit_redis


async def connect_rate_limit_redis() -> None:
    """Connect to Redis for rate limiting during startup."""
    global _rate_limit_redis
    _rate_limit_redis = redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    await _rate_limit_redis.ping()
    logger.info("Connected to Redis for rate limiting")


async def close_rate_limit_redis() -> None:
    """Close rate limiting Redis connection during shutdown."""
    global _rate_limit_redis
    if _rate_limit_redis:
        await _rate_limit_redis.close()


async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware using Redis with atomic operations."""
    # Skip rate limiting for health checks, docs, and prometheus metrics
    if request.url.path in ["/health", "/docs", "/openapi.json", "/redoc", "/metrics/prometheus"]:
        return await call_next(request)

    # Get client identifier (user ID from token or IP)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        # Use SHA-256 hash of the full token for security
        token_hash = hashlib.sha256(auth_header[7:].encode()).hexdigest()[:16]
        identifier = f"token:{token_hash}"
    else:
        # Fall back to IP address
        client_host = request.client.host if request.client else "unknown"
        identifier = f"ip:{client_host}"

    try:
        redis_client = await get_rate_limit_redis()
        if redis_client:
            # Rate limit key
            key = f"rate_limit:{identifier}"

            # Use atomic Lua script to check and increment
            script = redis_client.register_script(RATE_LIMIT_SCRIPT)
            current_count = await script(
                keys=[key],
                args=[settings.rate_limit_requests, settings.rate_limit_window],
            )

            if current_count > settings.rate_limit_requests:
                # Rate limit exceeded
                ttl = await redis_client.ttl(key)
                retry_after = ttl if ttl > 0 else settings.rate_limit_window
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": f"Rate limit exceeded. Maximum {settings.rate_limit_requests} requests per {settings.rate_limit_window} seconds.",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

    except Exception as e:
        # If rate limiting fails, log and continue (fail open for reliability)
        logger.error(f"Rate limiting error: {e}")

    return await call_next(request)
