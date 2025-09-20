"""Utility helpers for tracking per-user token usage in Redis."""

from __future__ import annotations

import logging
import time
from typing import Optional

import redis
from redis.exceptions import RedisError

from app.config.settings import get_effective_redis_url

logger = logging.getLogger(__name__)


class TokenUsageTracker:
    """Track daily token usage counts for a user via Redis."""

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        daily_ttl_seconds: int = 86400,
    ) -> None:
        self._redis_client: Optional[redis.Redis] = redis_client
        self._redis_url_signature: Optional[str] = "__injected__" if redis_client else None
        self._daily_ttl_seconds = daily_ttl_seconds

    def _close_client(self) -> None:
        if not self._redis_client:
            return
        try:
            self._redis_client.close()
        except RedisError:
            pass
        finally:
            self._redis_client = None
            self._redis_url_signature = None

    def _ensure_client(self) -> Optional[redis.Redis]:
        if self._redis_client is not None and self._redis_url_signature == "__injected__":
            return self._redis_client

        target_url = get_effective_redis_url()
        if not target_url:
            self._close_client()
            logger.info("Token usage tracking skipped (Redis not configured)")
            return None

        if self._redis_client is None or self._redis_url_signature != target_url:
            self._close_client()
            try:
                self._redis_client = redis.from_url(target_url)
                self._redis_url_signature = target_url
            except RedisError as exc:
                logger.warning(
                    "Failed to initialize Redis client for token tracking at %s: %s",
                    target_url,
                    exc,
                )
                self._redis_client = None
                self._redis_url_signature = None

        return self._redis_client

    @property
    def redis_client(self) -> Optional[redis.Redis]:
        return self._ensure_client()

    @redis_client.setter
    def redis_client(self, value: Optional[redis.Redis]) -> None:
        self._close_client()
        if value is None:
            return
        self._redis_client = value
        self._redis_url_signature = "__injected__"

    def increment_usage(self, user_id: str, token_count: int) -> int:
        client = self.redis_client
        if not client:
            return 0

        today = time.strftime("%Y-%m-%d")
        key = f"usage:{user_id}:{today}"

        try:
            new_usage = client.incrby(key, token_count)
            if new_usage == token_count:
                client.expire(key, self._daily_ttl_seconds)
        except RedisError as exc:
            logger.warning("Token usage tracking skipped due to Redis error: %s", exc)
            return 0

        return int(new_usage)

    def get_usage(self, user_id: str) -> int:
        client = self.redis_client
        if not client:
            return 0

        today = time.strftime("%Y-%m-%d")
        key = f"usage:{user_id}:{today}"

        try:
            usage = client.get(key)
        except RedisError as exc:
            logger.warning("Failed to read token usage from Redis: %s", exc)
            return 0

        if usage is None:
            return 0

        try:
            return int(usage)
        except (TypeError, ValueError):
            logger.warning("Unexpected token usage payload for %s: %r", user_id, usage)
            return 0


__all__ = ["TokenUsageTracker"]

