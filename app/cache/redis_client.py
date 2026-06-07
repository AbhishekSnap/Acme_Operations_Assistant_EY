"""
Redis is used for:
  - Session state: stores the last N agent turns per user (conversation memory)
  - Cached customer lookups: TTL 5 min to avoid repeated DB hits
  - Recent tool results: TTL 2 min so back-to-back identical queries skip the DB

Trade-off vs PostgreSQL:
  PostgreSQL is the source of truth for durable business data.
  Redis holds volatile, re-derivable state where latency matters.
  On Redis eviction or restart, the app degrades gracefully (cache miss → DB).
"""
import json
import redis.asyncio as aioredis
from config import settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


# Session memory helpers (conversation history per user)

SESSION_TTL = 3600  # 1 hour


async def get_session(user_id: str) -> list[dict]:
    r = get_redis()
    raw = await r.get(f"session:{user_id}")
    return json.loads(raw) if raw else []


async def append_session(user_id: str, role: str, content: str):
    r = get_redis()
    history = await get_session(user_id)
    history.append({"role": role, "content": content})
    if len(history) > 20:
        history = history[-20:]
    await r.setex(f"session:{user_id}", SESSION_TTL, json.dumps(history))


async def clear_session(user_id: str):
    r = get_redis()
    await r.delete(f"session:{user_id}")


# Generic cache helpers

async def cache_get(key: str):
    raw = await get_redis().get(key)
    return json.loads(raw) if raw else None


async def cache_set(key: str, value, ttl: int = 300):
    await get_redis().setex(key, ttl, json.dumps(value, default=str))
