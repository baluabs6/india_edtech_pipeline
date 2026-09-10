"""
redis_client.py
Thin async wrapper around Redis used for two things:
  1. Response caching (repeated /ask questions, /students/at-risk pages)
  2. Per-API-key sliding-window rate limiting

Using one Redis instance for both keeps infra simple — in Azure this maps to
a single Azure Cache for Redis resource.
"""
import hashlib
import json
import logging
import time

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self, url: str):
        self.client = redis.from_url(url, decode_responses=True)

    @staticmethod
    def make_key(*parts: str) -> str:
        raw = "|".join(str(p) for p in parts)
        return "cache:" + hashlib.sha256(raw.encode()).hexdigest()

    async def get_json(self, key: str):
        raw = await self.client.get(key)
        return json.loads(raw) if raw is not None else None

    async def set_json(self, key: str, value, ttl_seconds: int = 300):
        await self.client.set(key, json.dumps(value), ex=ttl_seconds)

    async def close(self):
        await self.client.aclose()

    # ---- Rate limiting: fixed-window counter per identity, per tier ----
    async def is_rate_limited(self, identity: str, limit: int, window_seconds: int,
                               tier: str = "default") -> bool:
        """
        Returns True if `identity` (e.g. an API key) has exceeded `limit`
        requests within the current `window_seconds` window for the given
        `tier`. Tiers are counted independently — e.g. a client hammering
        the expensive /v1/ask endpoint doesn't burn through the separate,
        more generous allowance for cheap /v1/students/at-risk reads.
        """
        bucket = int(time.time() // window_seconds)
        key = f"ratelimit:{tier}:{identity}:{bucket}"
        current = await self.client.incr(key)
        if current == 1:
            await self.client.expire(key, window_seconds)
        return current > limit

    # ---- Refresh token tracking: enables revocation + rotation ----
    async def store_refresh_jti(self, jti: str, client_id: str, ttl_seconds: int):
        await self.client.set(f"refresh_token:{jti}", client_id, ex=ttl_seconds)

    async def get_refresh_jti_owner(self, jti: str) -> str | None:
        return await self.client.get(f"refresh_token:{jti}")

    async def revoke_refresh_jti(self, jti: str):
        await self.client.delete(f"refresh_token:{jti}")
