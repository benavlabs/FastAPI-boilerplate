"""Module for initializing the cache backends."""

from ..config import CacheBackend
from ..config.settings import get_settings
from ..redis import cache_redis_client
from . import MEMCACHED_INSTALLED, REDIS_INSTALLED
from .provider import cache_provider

if MEMCACHED_INSTALLED:
    from .backends import MemcachedBackend, MemcachedSettings

if REDIS_INSTALLED:
    from .backends import RedisBackend, RedisSettings


async def initialize_cache() -> None:
    """Initialize the cache backends.

    This function initializes the cache backends based on the application settings.
    It is called during application startup.
    """
    settings = get_settings()

    if not settings.CACHE_ENABLED:
        return

    if settings.CACHE_BACKEND == CacheBackend.MEMCACHED.value:
        if not MEMCACHED_INSTALLED:
            raise ImportError("The aiomcache package is not installed. Please install it with 'pip install aiomcache'.")

        memcached_settings = MemcachedSettings(
            host=settings.CACHE_MEMCACHED_HOST,
            port=settings.CACHE_MEMCACHED_PORT,
            pool_size=settings.CACHE_MEMCACHED_POOL_SIZE,
            connect_timeout=settings.CACHE_MEMCACHED_CONNECT_TIMEOUT,
        )
        memcached_backend = MemcachedBackend(settings=memcached_settings)
        cache_provider.register_backend(CacheBackend.MEMCACHED.value, memcached_backend, default=True)

    elif settings.CACHE_BACKEND == CacheBackend.REDIS.value:
        if not REDIS_INSTALLED:
            raise ImportError("The redis package is not installed. Please install it with 'pip install redis'.")

        redis_settings = RedisSettings(
            host=settings.CACHE_REDIS_HOST,
            port=settings.CACHE_REDIS_PORT,
            db=settings.CACHE_REDIS_DB,
            password=settings.CACHE_REDIS_PASSWORD,
            connect_timeout=settings.CACHE_REDIS_CONNECT_TIMEOUT,
            pool_size=settings.CACHE_REDIS_POOL_SIZE,
        )
        redis_backend = RedisBackend(settings=redis_settings, client=cache_redis_client)
        cache_provider.register_backend(CacheBackend.REDIS.value, redis_backend, default=True)


async def close_cache() -> None:
    """Close all cache connections.

    This function should be called during application shutdown to clean up resources.
    """
    settings = get_settings()

    if not settings.CACHE_ENABLED:
        return

    if settings.CACHE_BACKEND == CacheBackend.MEMCACHED.value and MEMCACHED_INSTALLED:
        backend = cache_provider.get_backend(CacheBackend.MEMCACHED.value)
        if hasattr(backend, "client") and hasattr(backend.client, "close"):
            await backend.client.close()

    elif settings.CACHE_BACKEND == CacheBackend.REDIS.value and REDIS_INSTALLED:
        await cache_redis_client.aclose()
