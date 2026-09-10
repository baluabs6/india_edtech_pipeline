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
        # Keep the first part as a readable namespace prefix (e.g.
        # "students-at-risk", "ask") instead of hashing it away entirely.
        # This is what makes invalidate_namespace() below possible — an
        # opaque hash-only key can't be pattern-matched for bulk deletion,
        # which is exactly why deleted students could keep showing up in
        # cached /students/at-risk pages until TTL expiry.
        namespace = str(parts[0]) if parts else "default"
        raw = "|".join(str(p) for p in parts)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"cache:{namespace}:{digest}"

    async def get_json(self, key: str):
        raw = await self.client.get(key)
        return json.loads(raw) if raw is not None else None

    async def set_json(self, key: str, value, ttl_seconds: int = 300):
        await self.client.set(key, json.dumps(value), ex=ttl_seconds)

    async def close(self):
        await self.client.aclose()

    async def invalidate_namespace(self, namespace: str) -> int:
        """
        Deletes every cached entry under a namespace (e.g. every cached
        /students/at-risk page, across all limit/state combinations) via
        non-blocking SCAN + DELETE.

        Used on student deletion: we don't track which specific cached pages
        included a given student_id, so rather than leave a right-to-deletion
        gap where a cached page can keep serving a "deleted" student's data
        until TTL expiry, we invalidate the whole namespace. At a 300s
        default TTL this is cheap and the cache repopulates on next read.
        """
        cursor = 0
        pattern = f"cache:{namespace}:*"
        deleted = 0
        while True:
            cursor, keys = await self.client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                deleted += await self.client.delete(*keys)
            if cursor == 0:
                break
        return deleted

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
