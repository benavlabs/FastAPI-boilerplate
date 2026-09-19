"""Redis clients shared by application infrastructure."""

from redis.asyncio import Redis

from .config.settings import get_settings

settings = get_settings()


def _client(host: str, port: int, db: int, password: str | None, pool_size: int, timeout: int) -> Redis:
    return Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        socket_timeout=timeout,
        max_connections=pool_size,
        decode_responses=False,
    )


cache_redis_client = _client(
    settings.CACHE_REDIS_HOST,
    settings.CACHE_REDIS_PORT,
    settings.CACHE_REDIS_DB,
    settings.CACHE_REDIS_PASSWORD,
    settings.CACHE_REDIS_POOL_SIZE,
    settings.CACHE_REDIS_CONNECT_TIMEOUT,
)

rate_limiter_redis_client = _client(
    settings.RATE_LIMITER_REDIS_HOST,
    settings.RATE_LIMITER_REDIS_PORT,
    settings.RATE_LIMITER_REDIS_DB,
    settings.RATE_LIMITER_REDIS_PASSWORD,
    settings.RATE_LIMITER_REDIS_POOL_SIZE,
    settings.RATE_LIMITER_REDIS_CONNECT_TIMEOUT,
)
