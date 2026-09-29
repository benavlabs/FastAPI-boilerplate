"""Settings for the cache feature."""

from pydantic_settings import BaseSettings

from ..config.base import config
from ..config.enums import CacheBackend


class CacheSettings(BaseSettings):
    """Cache-related settings.

    This class defines settings for cache connections and behavior across
    the application.

    Attributes:
        CACHE_ENABLED: Whether to enable caching. Default is True.
        CACHE_BACKEND: The cache backend to use. Default is "memcached".

        # Memcached settings
        CACHE_MEMCACHED_HOST: Memcached server hostname. Default is "localhost".
        CACHE_MEMCACHED_PORT: Memcached server port. Default is 11211.
        CACHE_MEMCACHED_POOL_SIZE: Maximum number of connections in the pool. Default is 10.
        CACHE_MEMCACHED_CONNECT_TIMEOUT: Connection timeout in seconds. Default is 5.
            Note: This is not currently used by aiomcache.Client but is
            kept for API consistency with other cache backends.

        # Redis settings
        CACHE_REDIS_HOST: Redis server hostname. Default is "localhost".
        CACHE_REDIS_PORT: Redis server port. Default is 6379.
        CACHE_REDIS_DB: Redis database number. Default is 0.
        CACHE_REDIS_PASSWORD: Redis server password. Default is None.
        CACHE_REDIS_CONNECT_TIMEOUT: Connection timeout in seconds. Default is 5.
        CACHE_REDIS_POOL_SIZE: Maximum number of connections in the pool. Default is 10.

        DEFAULT_CACHE_EXPIRATION: Default expiration time for cache entries in seconds.
            Default is 3600 (1 hour).
    """

    CACHE_ENABLED: bool = config("CACHE_ENABLED", default=True, cast=bool)
    CACHE_BACKEND: str = config("CACHE_BACKEND", default=CacheBackend.MEMCACHED.value)

    CACHE_MEMCACHED_HOST: str = config("CACHE_MEMCACHED_HOST", default="localhost")
    CACHE_MEMCACHED_PORT: int = config("CACHE_MEMCACHED_PORT", default=11211, cast=int)
    CACHE_MEMCACHED_POOL_SIZE: int = config("CACHE_MEMCACHED_POOL_SIZE", default=10, cast=int)
    CACHE_MEMCACHED_CONNECT_TIMEOUT: int = config("CACHE_MEMCACHED_CONNECT_TIMEOUT", default=5, cast=int)

    CACHE_REDIS_HOST: str = config("CACHE_REDIS_HOST", default="localhost")
    CACHE_REDIS_PORT: int = config("CACHE_REDIS_PORT", default=6379, cast=int)
    CACHE_REDIS_DB: int = config("CACHE_REDIS_DB", default=0, cast=int)
    CACHE_REDIS_PASSWORD: str | None = config("CACHE_REDIS_PASSWORD", default=None)
    CACHE_REDIS_CONNECT_TIMEOUT: int = config("CACHE_REDIS_CONNECT_TIMEOUT", default=5, cast=int)
    CACHE_REDIS_POOL_SIZE: int = config("CACHE_REDIS_POOL_SIZE", default=10, cast=int)

    DEFAULT_CACHE_EXPIRATION: int = config("DEFAULT_CACHE_EXPIRATION", default=3600, cast=int)
