"""Whether the cache backend is reachable."""

import asyncio
from collections.abc import Awaitable
from contextlib import suppress
from typing import cast

import anyio

from ..composition import ReadinessCheck
from ..config.enums import CacheBackend
from ..config.settings import settings
from ..redis import redis_url
from .client import cache_redis_client

MEMCACHED_VERSION = b"version\r\n"


async def cache_is_reachable() -> None:
    """Raise unless the configured cache answers.

    A cache that is turned off, or one in the process, has nothing to reach. The
    memcached check asks on a connection of its own, which it then closes.
    """
    if not settings.CACHE_ENABLED:
        return

    if settings.CACHE_BACKEND == CacheBackend.REDIS.value:
        await cast(Awaitable[bool], cache_redis_client.ping())
        return

    if settings.CACHE_BACKEND == CacheBackend.MEMCACHED.value:
        await _memcached_answers(settings.CACHE_MEMCACHED_HOST, settings.CACHE_MEMCACHED_PORT)


async def _memcached_answers(host: str, port: int) -> None:
    """Raise unless memcached answers ``version`` on a socket of its own, which is then closed.

    The socket is closed even when the probe's timeout cancels the read, so a cancelled
    check leaves neither an open transport nor a connection holding an unread reply.
    """
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(MEMCACHED_VERSION)
        await writer.drain()
        answer = await reader.readline()
        if not answer.startswith(b"VERSION"):
            raise ConnectionError(f"memcached answered {answer!r} to a version command")
    finally:
        with anyio.CancelScope(shield=True):
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()


def cache_target() -> str | None:
    """The cache server this project talks to, or ``None`` when it talks to none."""
    if not settings.CACHE_ENABLED:
        return None

    if settings.CACHE_BACKEND == CacheBackend.MEMCACHED.value:
        return f"memcached://{settings.CACHE_MEMCACHED_HOST}:{settings.CACHE_MEMCACHED_PORT}"

    if settings.CACHE_BACKEND != CacheBackend.REDIS.value:
        return None

    return redis_url(
        settings.CACHE_REDIS_HOST,
        settings.CACHE_REDIS_PORT,
        settings.CACHE_REDIS_DB,
        settings.CACHE_REDIS_PASSWORD,
    )


readiness = ReadinessCheck("cache", cache_is_reachable, target=cache_target)
