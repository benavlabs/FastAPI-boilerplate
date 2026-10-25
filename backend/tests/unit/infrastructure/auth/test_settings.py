"""The session and limiter settings the accounts feature contributes."""

import os
from unittest.mock import patch

import pytest

from src.infrastructure.config.enums import RateLimiterBackend, SessionBackend
from src.infrastructure.config.settings import Settings, get_settings


class TestSessionSettings:
    """Test cases for session storage settings."""

    def test_session_redis_db_defaults_apart_from_other_services(self):
        """Sessions default to a Redis DB no other service uses."""
        settings = Settings()

        assert settings.SESSION_REDIS_DB == 2
        other_dbs = {
            getattr(settings, name)
            for name in ("CACHE_REDIS_DB", "RATE_LIMITER_REDIS_DB", "TASKIQ_REDIS_DB")
            if hasattr(settings, name)
        }
        assert settings.SESSION_REDIS_DB not in other_dbs

    def test_session_redis_url_defaults_to_cache_connection(self):
        """Without SESSION_REDIS_URL, sessions use the cache Redis connection on SESSION_REDIS_DB."""
        settings = Settings()

        assert settings.SESSION_REDIS_URL == "redis://localhost:6379/2"

    @patch.dict(
        os.environ,
        {
            "CACHE_REDIS_HOST": "redis-host",
            "CACHE_REDIS_PORT": "6380",
            "CACHE_REDIS_PASSWORD": "p@ss/word",
            "SESSION_REDIS_DB": "7",
        },
    )
    def test_session_redis_url_follows_cache_connection_with_encoded_password(self):
        """The cache password is URL-encoded so reserved characters don't break the session URL."""
        settings = Settings()

        assert settings.SESSION_REDIS_URL == "redis://:p%40ss%2Fword@redis-host:6380/7"

    @patch.dict(os.environ, {"SESSION_REDIS_URL": "rediss://default:secret@sessions.example.com:6380/0"})
    def test_session_redis_url_override_takes_precedence(self):
        """SESSION_REDIS_URL replaces the cache connection, for TLS or a dedicated instance."""
        settings = Settings()

        assert settings.SESSION_REDIS_URL == "rediss://default:secret@sessions.example.com:6380/0"


class TestRateLimiterSettings:
    """The limiter moved to crudauth; the memcached and fail-open knobs went with it."""

    def test_the_removed_memcached_and_fail_open_settings_are_gone(self):
        settings = get_settings()

        for name in (
            "RATE_LIMITER_FAIL_OPEN",
            "RATE_LIMITER_MEMCACHED_HOST",
            "RATE_LIMITER_MEMCACHED_PORT",
            "RATE_LIMITER_MEMCACHED_POOL_SIZE",
            "RATE_LIMITER_MEMCACHED_CONNECT_TIMEOUT",
        ):
            assert not hasattr(settings, name), name

    def test_the_rate_limiter_backend_names_a_supported_backend(self):
        assert RateLimiterBackend(get_settings().RATE_LIMITER_BACKEND)

    def test_the_backend_enums_accept_only_redis_and_memory(self):
        with pytest.raises(ValueError):
            SessionBackend("memcached")
        with pytest.raises(ValueError):
            RateLimiterBackend("memcached")
