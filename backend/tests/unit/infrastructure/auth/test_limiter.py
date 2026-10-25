"""The limiter behind the login lockout: its client, and which backend it uses."""

import pytest
from crudauth import DatabaseStore
from crudauth.ratelimit import RedisBackend
from crudauth.ratelimit.backends.database import DatabaseRateLimiterBackend

from src.infrastructure.auth import limiter as limiter_module
from src.infrastructure.auth.limiter import build_rate_limiter, rate_limiter_redis_client
from src.infrastructure.config.settings import settings
from src.infrastructure.database.session import get_session_factory


def _connection(client):
    return client.connection_pool


def _a_store() -> DatabaseStore:
    """A store on its own metadata, so a test never touches the app's tables."""
    return DatabaseStore(get_session_factory())


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

    def test_database_counts_in_the_projects_own_tables(self, monkeypatch):
        """Counters every worker shares, with no Redis to run."""
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "database")
        monkeypatch.setattr(limiter_module, "database_store", _a_store())

        backend = build_rate_limiter()

        assert isinstance(backend, DatabaseRateLimiterBackend)

    def test_database_without_a_store_fails_loudly(self, monkeypatch):
        """The store is built from the same settings, so this can only be a wiring mistake."""
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "database")
        monkeypatch.setattr(limiter_module, "database_store", None)

        with pytest.raises(ValueError, match="database store"):
            build_rate_limiter()

    def test_the_removed_memcached_backend_fails_loudly(self, monkeypatch):
        """A deployment still configured for memcached must not silently fall back to memory."""
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "memcached")

        with pytest.raises(ValueError, match="memcached"):
            build_rate_limiter()
