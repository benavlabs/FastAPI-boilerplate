"""Whether the cache backend is reachable."""

from collections.abc import Awaitable
from typing import cast

from ..composition import ReadinessCheck
from ..config.enums import CacheBackend
from ..config.settings import settings
from .client import cache_redis_client


async def cache_is_reachable() -> None:
    """Raise unless the configured cache answers.

    A project can run with the cache turned off, or on a backend this ping
    doesn't cover, in which case there is nothing to report.
    """
    if not settings.CACHE_ENABLED or settings.CACHE_BACKEND != CacheBackend.REDIS.value:
        return

    await cast(Awaitable[bool], cache_redis_client.ping())


readiness = ReadinessCheck("cache", cache_is_reachable)
