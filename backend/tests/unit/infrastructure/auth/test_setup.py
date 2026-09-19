"""Tests for the crudauth composition root wiring."""

import pytest
from crudauth import Principal
from starlette.requests import Request

from src.infrastructure.auth import setup
from src.infrastructure.config.settings import settings


def _request(path: str, client_host: str = "203.0.113.7") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": (client_host, 1234),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


class TestSessionRedisWiring:
    """Session storage uses SESSION_REDIS_URL, on a different DB than the cache by default."""

    def test_session_redis_db_is_not_the_cache_db(self):
        """By default a cache FLUSHDB must not reach the database holding sessions."""
        assert settings.SESSION_REDIS_DB != settings.CACHE_REDIS_DB
        assert settings.SESSION_REDIS_URL.endswith(f"/{settings.SESSION_REDIS_DB}")

    def test_redis_sessions_are_built_from_the_session_url(self, monkeypatch):
        monkeypatch.setattr(settings, "SESSION_BACKEND", "redis")

        transport = setup._session_transport()

        assert transport.redis_url == settings.SESSION_REDIS_URL

    def test_memory_sessions_carry_no_redis_url(self, monkeypatch):
        monkeypatch.setattr(settings, "SESSION_BACKEND", "memory")

        assert setup._session_transport().redis_url is None


class TestRateLimiterBackend:
    """RATE_LIMITER_BACKEND alone decides where the limiter and login lockout count."""

    def test_redis_uses_the_shared_limiter_client(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "redis")

        assert setup._rate_limiter() is not None

    def test_memory_leaves_crudauth_its_in_process_limiter(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "memory")

        assert setup._rate_limiter() is None

    def test_the_removed_memcached_backend_fails_loudly(self, monkeypatch):
        """A deployment still configured for memcached must not silently fall back to memory."""
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "memcached")

        with pytest.raises(ValueError, match="memcached"):
            setup._rate_limiter()


class TestApiRateLimitKey:
    """Each caller gets one budget per path, so one route can't exhaust another's."""

    def test_signed_in_callers_are_keyed_by_user_and_path(self):
        principal = Principal(user_id=42, transport="session")

        assert setup.api_rate_limit_key(_request("/api/v1/tiers/"), principal) == "user:42:/api/v1/tiers/"

    def test_anonymous_callers_are_keyed_by_ip_and_path(self):
        assert setup.api_rate_limit_key(_request("/api/v1/tiers/"), None) == "ip:203.0.113.7:/api/v1/tiers/"

    def test_different_paths_get_different_budgets(self):
        principal = Principal(user_id=42, transport="session")

        assert setup.api_rate_limit_key(_request("/api/v1/tiers/"), principal) != setup.api_rate_limit_key(
            _request("/api/v1/rate-limits/"), principal
        )


class TestOAuthWiring:
    """The callback URI crudauth sends to the provider matches the route that serves it."""

    def test_the_callback_lives_under_the_api_prefix(self):
        assert setup.OAUTH_PREFIX == "/api/v1/auth/oauth"
