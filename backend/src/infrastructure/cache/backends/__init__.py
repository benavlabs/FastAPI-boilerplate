"""
Caching backend implementations.

This module contains implementations of various cache backends that follow the
CacheBackend interface. ``.memcached`` ships only with ``cache.backend=memcached``, so nothing
here imports it; ``initialize`` loads it by name when that backend is configured.
"""

from importlib.util import find_spec

REDIS_INSTALLED = find_spec("redis.asyncio") is not None

if REDIS_INSTALLED:
    from .redis import RedisBackend, RedisSettings
else:
    RedisBackend = None  # type: ignore
    RedisSettings = None  # type: ignore

__all__ = ["RedisBackend", "RedisSettings"]
