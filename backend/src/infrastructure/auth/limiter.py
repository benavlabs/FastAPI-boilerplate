"""The limiter behind crudauth's login lockout, and the client it runs on."""

from crudauth.ratelimit import RateLimiterBackend, redis_rate_limiter

from ..config.enums import RateLimiterBackend as RateLimiterBackendName
from ..config.settings import settings
from ..redis import make_redis_client

rate_limiter_redis_client = make_redis_client(
    settings.RATE_LIMITER_REDIS_HOST,
    settings.RATE_LIMITER_REDIS_PORT,
    settings.RATE_LIMITER_REDIS_DB,
    settings.RATE_LIMITER_REDIS_PASSWORD,
    settings.RATE_LIMITER_REDIS_POOL_SIZE,
    settings.RATE_LIMITER_REDIS_CONNECT_TIMEOUT,
)


def build_rate_limiter() -> RateLimiterBackend | None:
    """The limiter backend ``RATE_LIMITER_BACKEND`` names; ``None`` lets crudauth use memory."""
    backend = settings.RATE_LIMITER_BACKEND
    if backend == RateLimiterBackendName.REDIS:
        return redis_rate_limiter(client=rate_limiter_redis_client)
    if backend == RateLimiterBackendName.MEMORY:
        return None
    raise ValueError(
        f"RATE_LIMITER_BACKEND={backend!r} isn't supported; use 'redis' or 'memory'. "
        "The memcached rate limiter was removed when rate limiting moved to crudauth."
    )
