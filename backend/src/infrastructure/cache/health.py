"""Whether the cache backend is reachable."""

from collections.abc import Awaitable
from typing import cast

from ..composition import ReadinessCheck
from ..config.enums import CacheBackend
from ..config.settings import settings
from ..redis import redis_url
from .backends.memcached import MemcachedBackend
from .client import cache_redis_client
from .provider import cache_provider


async def cache_is_reachable() -> None:
    """Raise unless the configured cache answers.

    A project can run with the cache turned off, in which case there is nothing
    to report.
    """
    if not settings.CACHE_ENABLED:
        return

    if settings.CACHE_BACKEND == CacheBackend.REDIS.value:
        await cast(Awaitable[bool], cache_redis_client.ping())
        return

    if settings.CACHE_BACKEND == CacheBackend.MEMCACHED.value:
        backend = cast(MemcachedBackend, cache_provider.get_backend(CacheBackend.MEMCACHED.value))
        await backend.client.version()


def cache_target() -> str | None:
    """The cache server this project talks to."""
    if not settings.CACHE_ENABLED:
        return None

    if settings.CACHE_BACKEND == CacheBackend.MEMCACHED.value:
        return f"memcached://{settings.CACHE_MEMCACHED_HOST}:{settings.CACHE_MEMCACHED_PORT}"

    return redis_url(
        settings.CACHE_REDIS_HOST,
        settings.CACHE_REDIS_PORT,
        settings.CACHE_REDIS_DB,
        settings.CACHE_REDIS_PASSWORD,
    )


readiness = ReadinessCheck("cache", cache_is_reachable, target=cache_target)
