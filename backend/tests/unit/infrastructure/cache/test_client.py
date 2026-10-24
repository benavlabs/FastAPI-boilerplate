"""The Redis client the cache owns, and where it is injected."""

from src.infrastructure.cache import initialize
from src.infrastructure.cache.client import cache_redis_client
from src.infrastructure.cache.settings import CacheSettings
from src.infrastructure.config.settings import settings


def _connection(client):
    return client.connection_pool


class TestClientSettings:
    """The client follows the cache's settings, not another service's."""

    def test_cache_client_uses_the_cache_settings(self):
        pool = _connection(cache_redis_client)
        kwargs = pool.connection_kwargs

        assert kwargs["host"] == settings.CACHE_REDIS_HOST
        assert kwargs["port"] == settings.CACHE_REDIS_PORT
        assert kwargs["db"] == settings.CACHE_REDIS_DB
        assert kwargs["socket_timeout"] == settings.CACHE_REDIS_CONNECT_TIMEOUT
        assert kwargs["decode_responses"] is False
        assert pool.max_connections == settings.CACHE_REDIS_POOL_SIZE


class TestInjection:
    """The cache backend is handed the shared client instead of opening its own."""

    async def test_the_cache_backend_reuses_the_shared_client(self, monkeypatch):
        monkeypatch.setattr(settings, "CACHE_BACKEND", "redis")
        captured: dict[str, object] = {}

        class RecordingBackend:
            def __init__(self, settings, client):
                captured["client"] = client

        monkeypatch.setattr(initialize, "RedisBackend", RecordingBackend)
        monkeypatch.setattr(initialize.cache_provider, "register_backend", lambda *args, **kwargs: None)

        await initialize.initialize_cache()

        assert captured["client"] is cache_redis_client


def test_the_default_backend_is_the_one_the_compose_files_provide():
    """An env file without CACHE_BACKEND must not switch the app onto a service nothing runs."""
    assert CacheSettings().CACHE_BACKEND == "redis"
