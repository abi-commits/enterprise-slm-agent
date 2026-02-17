"""Redis caching integration for the consolidated API Service.

Copied from services/gateway/cache.py with updated module context.
Provides caching for search results, LLM responses, and embeddings.
"""

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as redis
from redis.asyncio import Redis

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class CacheManager:
    """Redis caching manager for the API Service."""

    def __init__(self):
        """Initialize the cache manager."""
        self._redis: Optional[Redis] = None

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self._redis = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            logger.info("Connected to Redis cache")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._redis = None

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()
            logger.info("Disconnected from Redis cache")

    @property
    def redis(self) -> Optional[Redis]:
        """Get the Redis client."""
        return self._redis

    def _hash_key(self, key: str) -> str:
        """Generate a hash for the given key."""
        return hashlib.sha256(key.encode()).hexdigest()

    async def get_search_cache(
        self,
        query: str,
        user_role: str,
    ) -> Optional[list[dict]]:
        """
        Get cached search results.

        Args:
            query: Search query
            user_role: User role for RBAC

        Returns:
            Cached search results or None
        """
        if not self._redis:
            return None

        try:
            key = f"search:{user_role}:{self._hash_key(query)}"
            cached = await self._redis.get(key)
            if cached:
                logger.debug(f"Cache hit for search: {query[:50]}...")
                return json.loads(cached)
            return None
        except Exception as e:
            logger.error(f"Error getting search cache: {e}")
            return None

    async def set_search_cache(
        self,
        query: str,
        user_role: str,
        results: list[dict],
    ) -> None:
        """
        Cache search results.

        Args:
            query: Search query
            user_role: User role for RBAC
            results: Search results to cache
        """
        if not self._redis:
            return

        try:
            key = f"search:{user_role}:{self._hash_key(query)}"
            await self._redis.setex(
                key,
                settings.cache_search_ttl,
                json.dumps(results),
            )
            logger.debug(f"Cached search results for: {query[:50]}...")
        except Exception as e:
            logger.error(f"Error setting search cache: {e}")

    async def get_llm_response_cache(self, prompt: str) -> Optional[str]:
        """
        Get cached LLM response.

        Args:
            prompt: Prompt hash

        Returns:
            Cached LLM response or None
        """
        if not self._redis:
            return None

        try:
            key = f"llm_response:{self._hash_key(prompt)}"
            cached = await self._redis.get(key)
            if cached:
                logger.debug("Cache hit for LLM response")
                return cached
            return None
        except Exception as e:
            logger.error(f"Error getting LLM response cache: {e}")
            return None

    async def set_llm_response_cache(
        self,
        prompt: str,
        response: str,
    ) -> None:
        """
        Cache LLM response.

        Args:
            prompt: Prompt hash
            response: LLM response to cache
        """
        if not self._redis:
            return

        try:
            key = f"llm_response:{self._hash_key(prompt)}"
            await self._redis.setex(
                key,
                settings.cache_llm_response_ttl,
                response,
            )
            logger.debug("Cached LLM response")
        except Exception as e:
            logger.error(f"Error setting LLM response cache: {e}")

    async def get_embedding_cache(self, query: str) -> Optional[list[float]]:
        """
        Get cached embedding.

        Args:
            query: Query string

        Returns:
            Cached embedding or None
        """
        if not self._redis:
            return None

        try:
            key = f"embedding:{self._hash_key(query)}"
            cached = await self._redis.get(key)
            if cached:
                logger.debug("Cache hit for embedding")
                return json.loads(cached)
            return None
        except Exception as e:
            logger.error(f"Error getting embedding cache: {e}")
            return None

    async def set_embedding_cache(
        self,
        query: str,
        embedding: list[float],
    ) -> None:
        """
        Cache embedding.

        Args:
            query: Query string
            embedding: Embedding vector to cache
        """
        if not self._redis:
            return

        try:
            key = f"embedding:{self._hash_key(query)}"
            await self._redis.setex(
                key,
                settings.cache_embedding_ttl,
                json.dumps(embedding),
            )
            logger.debug("Cached embedding")
        except Exception as e:
            logger.error(f"Error setting embedding cache: {e}")

    async def invalidate_search_cache(self, user_role: Optional[str] = None) -> None:
        """
        Invalidate search caches.

        Args:
            user_role: Specific role to invalidate, or None for all
        """
        if not self._redis:
            return

        try:
            if user_role:
                pattern = f"search:{user_role}:*"
            else:
                pattern = "search:*"

            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await self._redis.delete(*keys)
                logger.info(f"Invalidated {len(keys)} search cache entries")
        except Exception as e:
            logger.error(f"Error invalidating search cache: {e}")

    async def invalidate_llm_cache(self) -> None:
        """Invalidate all LLM response caches."""
        if not self._redis:
            return

        try:
            keys = []
            async for key in self._redis.scan_iter(match="llm_response:*"):
                keys.append(key)

            if keys:
                await self._redis.delete(*keys)
                logger.info(f"Invalidated {len(keys)} LLM response cache entries")
        except Exception as e:
            logger.error(f"Error invalidating LLM cache: {e}")


# Global cache manager instance
cache_manager = CacheManager()


async def get_cache() -> CacheManager:
    """Get the cache manager instance."""
    return cache_manager
