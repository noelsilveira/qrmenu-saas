import json
import time
import redis.asyncio as redis
from typing import Optional, Any, Dict
from app.core.config import settings

_redis_pool: Optional[redis.Redis] = None
_in_memory_cache: Dict[str, tuple] = {}


async def get_redis() -> Optional[redis.Redis]:
    global _redis_pool
    if _redis_pool is None:
        try:
            _redis_pool = redis.from_url(settings.REDIS_URI, decode_responses=True)
            await _redis_pool.ping()
        except Exception:
            _redis_pool = None
    return _redis_pool


async def close_redis():
    global _redis_pool
    if _redis_pool:
        await _redis_pool.close()
        _redis_pool = None


def _memory_get(key: str) -> Optional[Any]:
    entry = _in_memory_cache.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.time() > expires_at:
        del _in_memory_cache[key]
        return None
    return value


def _memory_set(key: str, value: Any, ttl_seconds: int = 300):
    _in_memory_cache[key] = (value, time.time() + ttl_seconds)


def _memory_delete(key: str):
    _in_memory_cache.pop(key, None)


def _memory_delete_pattern(pattern: str):
    keys_to_delete = [k for k in _in_memory_cache if pattern in k or k.startswith(pattern.rstrip("*"))]
    for k in keys_to_delete:
        _in_memory_cache.pop(k, None)


async def cache_get(key: str) -> Optional[Any]:
    try:
        r = await get_redis()
        if r is None:
            return _memory_get(key)
        val = await r.get(key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return val
    except Exception:
        return _memory_get(key)


async def cache_set(key: str, value: Any, ttl_seconds: int = 300):
    try:
        r = await get_redis()
        if r is None:
            _memory_set(key, value, ttl_seconds)
            return
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        await r.setex(key, ttl_seconds, value)
    except Exception:
        _memory_set(key, value, ttl_seconds)


async def cache_delete(key: str):
    try:
        r = await get_redis()
        if r is None:
            _memory_delete(key)
            return
        await r.delete(key)
    except Exception:
        _memory_delete(key)


async def cache_delete_pattern(pattern: str):
    try:
        r = await get_redis()
        if r is None:
            _memory_delete_pattern(pattern)
            return
        keys = await r.keys(pattern)
        if keys:
            await r.delete(*keys)
    except Exception:
        _memory_delete_pattern(pattern)
