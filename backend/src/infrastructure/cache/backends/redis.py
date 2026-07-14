import json
from typing import Any

try:
    from redis.asyncio import Redis
except ImportError:
    raise ImportError(
        "The redis package is not installed. Please install it with 'pip install redis' or 'pip install -e \".[redis]\"'"
    )

from pydantic import BaseModel

from ...config.settings import get_settings
from ..base import CacheBackend

settings = get_settings()


class RedisSettings(BaseModel):
    """Settings for Redis connection.

    This class defines the configuration for connecting to a Redis server.

    Attributes:
        host: Redis server hostname. Default is "localhost".
        port: Redis server port. Default is 6379.
        db: Redis database number. Default is 0.
        password: Redis server password. Default is None.
        connect_timeout: Connection timeout in seconds. Default is 5.
        pool_size: Maximum number of connections in the pool. Default is 10.
    """

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    connect_timeout: int = 5
    pool_size: int = 10


class RedisBackend(CacheBackend):
    """Redis implementation of the cache backend."""

    def __init__(self, settings: RedisSettings | None = None):
        """Initialize the Redis backend.

        Args:
            settings: Custom settings for Redis connection. If None, default settings are used.
        """
        self.settings = settings or RedisSettings()
        self.client = Redis(
            host=self.settings.host,
            port=self.settings.port,
            db=self.settings.db,
            password=self.settings.password,
            socket_timeout=self.settings.connect_timeout,
            max_connections=self.settings.pool_size,
        )

    async def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: The cache key to get.

        Returns:
            The cached value or None if the key doesn't exist.
        """
        result = await self.client.get(key)

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
        if not isinstance(value, bytes | str | int | float | bool):
            value_bytes = json.dumps(value).encode("utf-8")
        elif isinstance(value, str):
            value_bytes = value.encode("utf-8")
        elif isinstance(value, bytes):
            value_bytes = value
        else:
            value_bytes = str(value).encode("utf-8")

        await self.client.set(key, value_bytes, ex=expiration)

    async def delete(self, key: str) -> None:
        """Delete a key from the cache.

        Args:
            key: The cache key to delete.
        """
        await self.client.delete(key)

    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching a pattern.

        Pages the ``SCAN`` cursor to completion so every match is removed, not just
        the first batch. Each batch is deleted as it is scanned.

        Args:
            pattern: The pattern to match against keys.
        """
        cursor = 0
        while True:
            cursor, keys = await self.client.scan(cursor=cursor, match=pattern + "*", count=100)
            if keys:
                await self.client.delete(*keys)
            if cursor == 0:
                break

    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: The cache key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        result = await self.client.exists(key)
        return bool(result > 0)

    async def clear(self) -> None:
        """Clear the entire cache."""
        await self.client.flushdb()

    async def ping(self) -> bool:
        """Check if the cache is available.

        Returns:
            True if the cache is available, False otherwise.
        """
        try:
            result = await self.client.ping()  # type: ignore[misc]
            return bool(result)
        except Exception:
            return False
