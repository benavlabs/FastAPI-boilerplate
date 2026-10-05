"""The limiter behind the login lockout: its client, and which backend it uses."""

import pytest
from crudauth.ratelimit import RedisBackend

from src.infrastructure.auth.limiter import build_rate_limiter, rate_limiter_redis_client
from src.infrastructure.config.settings import settings


def _connection(client):
    return client.connection_pool


class TestClientSettings:
    """The client follows the rate limiter's settings, not the cache's."""

    def test_rate_limiter_client_uses_the_rate_limiter_settings(self):
        pool = _connection(rate_limiter_redis_client)
        kwargs = pool.connection_kwargs

        assert kwargs["host"] == settings.RATE_LIMITER_REDIS_HOST
        assert kwargs["port"] == settings.RATE_LIMITER_REDIS_PORT
        assert kwargs["db"] == settings.RATE_LIMITER_REDIS_DB
        assert kwargs["socket_timeout"] == settings.RATE_LIMITER_REDIS_CONNECT_TIMEOUT
        assert kwargs["decode_responses"] is False
        assert pool.max_connections == settings.RATE_LIMITER_REDIS_POOL_SIZE


class TestRateLimiterBackend:
    """RATE_LIMITER_BACKEND alone decides where the limiter and login lockout count."""

    def test_redis_uses_the_shared_limiter_client(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "redis")
        monkeypatch.setattr(settings, "SESSION_BACKEND", "memory")

        backend = build_rate_limiter()

        assert isinstance(backend, RedisBackend)
        assert backend.client is rate_limiter_redis_client

    def test_memory_leaves_crudauth_its_in_process_limiter(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "memory")

        assert build_rate_limiter() is None

    def test_the_removed_memcached_backend_fails_loudly(self, monkeypatch):
        """A deployment still configured for memcached must not silently fall back to memory."""
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "memcached")

        with pytest.raises(ValueError, match="memcached"):
            build_rate_limiter()
