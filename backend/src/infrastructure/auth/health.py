"""Whether the servers accounts needs are reachable."""

from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis

from ..composition import ReadinessCheck
from ..config.enums import RateLimiterBackend, SessionBackend
from ..config.settings import settings
from ..redis import redis_url
from .limiter import rate_limiter_redis_client


async def limiter_is_reachable() -> None:
    """Raise unless the Redis the login lockout counts in answers.

    The lockout fails closed, so with this server unreachable every login is
    refused. In-process counting has nothing to reach.
    """
    if settings.RATE_LIMITER_BACKEND != RateLimiterBackend.REDIS.value:
        return

    await cast(Awaitable[bool], rate_limiter_redis_client.ping())


def limiter_target() -> str | None:
    """The server the login lockout counts in."""
    if settings.RATE_LIMITER_BACKEND != RateLimiterBackend.REDIS.value:
        return None

    return redis_url(
        settings.RATE_LIMITER_REDIS_HOST,
        settings.RATE_LIMITER_REDIS_PORT,
        settings.RATE_LIMITER_REDIS_DB,
        settings.RATE_LIMITER_REDIS_PASSWORD,
    )


async def sessions_are_reachable() -> None:
    """Raise unless the Redis holding the sessions answers."""
    if settings.SESSION_BACKEND != SessionBackend.REDIS.value:
        return

    client = Redis.from_url(settings.SESSION_REDIS_URL)
    try:
        await cast(Awaitable[bool], client.ping())
    finally:
        await client.aclose()


def sessions_target() -> str | None:
    """The server the sessions live in."""
    return settings.SESSION_REDIS_URL if settings.SESSION_BACKEND == SessionBackend.REDIS.value else None


limiter_readiness = ReadinessCheck("rate_limiter", limiter_is_reachable, target=limiter_target)
sessions_readiness = ReadinessCheck("sessions", sessions_are_reachable, target=sessions_target)
