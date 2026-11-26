import json
from typing import Any

import aiomcache
from pydantic import BaseModel

from ...config.settings import get_settings
from ..base import CacheBackend
from ..exceptions import PatternMatchingNotSupportedError

settings = get_settings()


class MemcachedSettings(BaseModel):
    """Settings for Memcached connection.

    This class defines the configuration for connecting to a Memcached server.

    Attributes:
        host: Memcached server hostname. Default is "localhost".
        port: Memcached server port. Default is 11211.
        pool_size: Maximum number of connections in the pool. Default is 10.
        connect_timeout: Connection timeout in seconds. Default is 5.
            Note: This parameter is not currently used by aiomcache.Client but is
            kept for API consistency with other cache backends.
    """

    host: str = "localhost"
    port: int = 11211
    pool_size: int = 10
    connect_timeout: int = 5


class MemcachedBackend(CacheBackend):
    """Memcached implementation of the cache backend."""

    def __init__(self, settings: MemcachedSettings | None = None):
        """Initialize the Memcached backend.

        Args:
            settings: Custom settings for Memcached connection. If None, default settings are used.
        """
        self.settings = settings or MemcachedSettings()
        self.client = aiomcache.Client(
            host=self.settings.host,
            port=self.settings.port,
            pool_size=self.settings.pool_size,
        )

    async def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: The cache key to get.

        Returns:
            The cached value or None if the key doesn't exist.
        """
        key_bytes = key.encode("utf-8")
        result = await self.client.get(key_bytes)

        if result is None:
            return None

        try:
            return json.loads(result.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return result

    async def set(self, key: str, value: Any, expiration: int = 3600) -> None:
        """Set a value in the cache.

        Args:
            key: The cache key to set.
            value: The value to cache.
            expiration: Time in seconds before the key expires (default: 3600).
        """
        key_bytes = key.encode("utf-8")

        if not isinstance(value, bytes | str | int | float | bool):
            value_bytes = json.dumps(value).encode("utf-8")
        elif isinstance(value, str):
            value_bytes = value.encode("utf-8")
        elif isinstance(value, bytes):
            value_bytes = value
        else:
            value_bytes = str(value).encode("utf-8")

        await self.client.set(key_bytes, value_bytes, exptime=expiration)

    async def delete(self, key: str) -> None:
        """Delete a key from the cache.

        Args:
            key: The cache key to delete.
        """
        key_bytes = key.encode("utf-8")
        await self.client.delete(key_bytes)

    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching a pattern.

        Args:
            pattern: The pattern to match against keys.

        Raises:
            PatternMatchingNotSupportedError: Always raised because Memcached doesn't
                support pattern matching for keys.
        """
        raise PatternMatchingNotSupportedError(pattern)

    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: The cache key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        result = await self.get(key)
        return result is not None

    async def clear(self) -> None:
        """Clear the entire cache."""
        await self.client.flush_all()

    async def ping(self) -> bool:
        """Check if the cache is available.

        Returns:
            True if the cache is available, False otherwise.
        """
        try:
            test_key = b"_memcached_ping_test"
            await self.client.set(test_key, b"1", exptime=1)
            result = await self.client.get(test_key)
            return bool(result == b"1")
        except Exception:
            return False
