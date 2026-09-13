"""Tests for the crudauth composition root wiring."""

from src.infrastructure.auth import setup
from src.infrastructure.config.settings import settings


class TestSessionRedisWiring:
    """Session storage must use SESSION_REDIS_URL, on a different DB than the cache by default."""

    def test_session_redis_url_comes_from_session_settings(self):
        """The URL handed to crudauth is SESSION_REDIS_URL."""
        assert setup._session_redis_url == settings.SESSION_REDIS_URL

    def test_session_redis_db_is_not_the_cache_db(self):
        """By default a cache FLUSHDB must not reach the database holding sessions."""
        assert settings.SESSION_REDIS_DB != settings.CACHE_REDIS_DB
        assert setup._session_redis_url.endswith(f"/{settings.SESSION_REDIS_DB}")

    def test_session_transport_receives_session_redis_url(self):
        """The session transport is built from the session URL when Redis-backed."""
        transport = setup.auth.transports[0]

        expected = setup._session_redis_url if setup._use_redis else None
        assert transport.redis_url == expected
