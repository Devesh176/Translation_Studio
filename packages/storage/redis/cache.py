import hashlib
import json
import os
from typing import Optional, Any


class TranslationCache:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._memory_cache: dict[str, str] = {}
        self._redis_client = None

    def _get_redis(self):
        if self._redis_client is None:
            try:
                import redis.asyncio as aioredis
                self._redis_client = aioredis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                )
            except Exception:
                self._redis_client = False
        return self._redis_client

    @staticmethod
    def compute_cache_key(
        source_text: str,
        source_language: str,
        target_language: str,
        provider: str,
        model: str,
        prompt_version: str,
        terminology_version: str = "v1",
    ) -> str:
        raw = f"{source_text}|{source_language}|{target_language}|{provider}|{model}|{prompt_version}|{terminology_version}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def get(self, key: str) -> Optional[str]:
        # Try redis, fallback to memory
        client = self._get_redis()
        if client:
            try:
                return await client.get(f"trans:{key}")
            except Exception:
                # Mark redis unavailable so subsequent calls immediately use in-memory cache
                self._redis_client = False
        return self._memory_cache.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int = 86400 * 30) -> None:
        client = self._get_redis()
        if client:
            try:
                await client.setex(f"trans:{key}", ttl_seconds, value)
                return
            except Exception:
                # Mark redis unavailable so subsequent calls immediately use in-memory cache
                self._redis_client = False
        self._memory_cache[key] = value

