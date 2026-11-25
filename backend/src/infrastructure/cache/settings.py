"""Settings for the cache feature."""

from ..config.base import EnvSettings
from ..config.enums import CacheBackend


class CacheSettings(EnvSettings):
    """Cache-related settings.

    This class defines settings for cache connections and behavior across
    the application.

    Attributes:
        CACHE_ENABLED: Whether to enable caching. Default is True.
        CACHE_BACKEND: The cache backend to use. Default is "redis", which is what
            the compose files and .env.example provide.

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
        CACHE_REDIS_SSL: Whether the connection speaks TLS. Default is False.
        CACHE_REDIS_CONNECT_TIMEOUT: Connection timeout in seconds. Default is 5.
        CACHE_REDIS_POOL_SIZE: Maximum number of connections in the pool. Default is 10.
    """

    CACHE_ENABLED: bool = True
    CACHE_BACKEND: str = CacheBackend.REDIS.value

    CACHE_MEMCACHED_HOST: str = "localhost"
    CACHE_MEMCACHED_PORT: int = 11211
    CACHE_MEMCACHED_POOL_SIZE: int = 10
    CACHE_MEMCACHED_CONNECT_TIMEOUT: int = 5

    CACHE_REDIS_HOST: str = "localhost"
    CACHE_REDIS_PORT: int = 6379
    CACHE_REDIS_DB: int = 0
    CACHE_REDIS_PASSWORD: str | None = None
    CACHE_REDIS_SSL: bool = False
    CACHE_REDIS_CONNECT_TIMEOUT: int = 5
    CACHE_REDIS_POOL_SIZE: int = 10
