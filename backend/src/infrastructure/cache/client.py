"""The Redis client the cache feature owns."""

from ..config.settings import settings
from ..redis import make_redis_client

cache_redis_client = make_redis_client(
    settings.CACHE_REDIS_HOST,
    settings.CACHE_REDIS_PORT,
    settings.CACHE_REDIS_DB,
    settings.CACHE_REDIS_PASSWORD,
    settings.CACHE_REDIS_POOL_SIZE,
    settings.CACHE_REDIS_CONNECT_TIMEOUT,
)
