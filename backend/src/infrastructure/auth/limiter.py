"""The limiter behind crudauth's login lockout, and the client it runs on."""

from crudauth.ratelimit import MemoryRateLimiterBackend, RateLimiterBackend, redis_rate_limiter

from ..config.enums import RateLimiterBackend as RateLimiterBackendName
from ..config.settings import settings
from ..redis import make_redis_client
from .store import database_store

rate_limiter_redis_client = make_redis_client(
    settings.RATE_LIMITER_REDIS_HOST,
    settings.RATE_LIMITER_REDIS_PORT,
    settings.RATE_LIMITER_REDIS_DB,
    settings.RATE_LIMITER_REDIS_PASSWORD,
    settings.RATE_LIMITER_REDIS_POOL_SIZE,
    settings.RATE_LIMITER_REDIS_CONNECT_TIMEOUT,
)


def build_rate_limiter(prefix: str | None = None) -> RateLimiterBackend | None:
    """The limiter backend ``RATE_LIMITER_BACKEND`` names; ``None`` lets crudauth use memory.

    Args:
        prefix: Put before every key, for a caller whose counters must not meet anybody
            else's. Keys are otherwise shared: a lockout names them from the identifier it
            was handed, so two callers on one backend write each other's budgets. With a
            prefix the memory backend is built here rather than left to crudauth, since a
            backend of its own is what isolates it.

    Raises:
        ValueError: ``RATE_LIMITER_BACKEND`` names a backend this project has none for, or
            names ``database`` without a store.
    """
    backend = settings.RATE_LIMITER_BACKEND
    if backend == RateLimiterBackendName.REDIS:
        client = rate_limiter_redis_client
        return redis_rate_limiter(client=client) if prefix is None else redis_rate_limiter(client=client, prefix=prefix)
    if backend == RateLimiterBackendName.DATABASE:
        if database_store is None:
            raise ValueError("RATE_LIMITER_BACKEND='database' needs a database store")
        return database_store.rate_limiter() if prefix is None else database_store.rate_limiter(prefix=prefix)
    if backend == RateLimiterBackendName.MEMORY:
        return MemoryRateLimiterBackend() if prefix is not None else None
    raise ValueError(
        f"RATE_LIMITER_BACKEND={backend!r} isn't supported; use "
        f"{', '.join(repr(name.value) for name in RateLimiterBackendName)}. "
        "The memcached rate limiter was removed when rate limiting moved to crudauth."
    )
