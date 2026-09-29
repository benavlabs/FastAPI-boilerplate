"""The limiter behind the login lockout: its client, and which backend it uses."""

from typing import cast

import pytest
from crudauth.ratelimit import RateLimiterBackend

from src.infrastructure.auth.limiter import build_rate_limiter, rate_limiter_redis_client
from src.infrastructure.auth.setup import auth
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

        assert backend is not None
        assert backend.client is rate_limiter_redis_client

    def test_memory_leaves_crudauth_its_in_process_limiter(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "memory")

        assert build_rate_limiter() is None

    def test_the_removed_memcached_backend_fails_loudly(self, monkeypatch):
        """A deployment still configured for memcached must not silently fall back to memory."""
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "memcached")

        with pytest.raises(ValueError, match="memcached"):
            build_rate_limiter()


class TestLockoutFailureMode:
    """A limiter outage must not become a way to switch the login lockout off."""

    @pytest.mark.asyncio
    async def test_the_lockout_refuses_logins_while_the_backend_is_down(self):
        """Documented in docs/user-guide/authentication/sessions.md: it fails closed."""

        class UnreachableBackend:
            async def get_ttl(self, key):
                raise ConnectionError("limiter redis is down")

        policy = auth._build_lockout(None, cast(RateLimiterBackend, UnreachableBackend()))
        allowed, remaining, retry_after = await policy.check_and_record("203.0.113.7", "victim@example.com")

        assert allowed is False
        assert remaining == 0
        assert retry_after > 0
