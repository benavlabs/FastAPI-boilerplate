"""The shared Redis clients, and where they are injected."""

from src.infrastructure import redis
from src.infrastructure.cache import initialize
from src.infrastructure.config.settings import settings


def _connection(client):
    return client.connection_pool


class TestClientSettings:
    """Each client follows its own settings, not the other service's."""

    def test_cache_client_uses_the_cache_settings(self):
        pool = _connection(redis.cache_redis_client)
        kwargs = pool.connection_kwargs

        assert kwargs["host"] == settings.CACHE_REDIS_HOST
        assert kwargs["port"] == settings.CACHE_REDIS_PORT
        assert kwargs["db"] == settings.CACHE_REDIS_DB
        assert kwargs["socket_timeout"] == settings.CACHE_REDIS_CONNECT_TIMEOUT
        assert kwargs["decode_responses"] is False
        assert pool.max_connections == settings.CACHE_REDIS_POOL_SIZE

    def test_rate_limiter_client_uses_the_rate_limiter_settings(self):
        pool = _connection(redis.rate_limiter_redis_client)
        kwargs = pool.connection_kwargs

        assert kwargs["host"] == settings.RATE_LIMITER_REDIS_HOST
        assert kwargs["port"] == settings.RATE_LIMITER_REDIS_PORT
        assert kwargs["db"] == settings.RATE_LIMITER_REDIS_DB
        assert kwargs["socket_timeout"] == settings.RATE_LIMITER_REDIS_CONNECT_TIMEOUT
        assert kwargs["decode_responses"] is False
        assert pool.max_connections == settings.RATE_LIMITER_REDIS_POOL_SIZE


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

        assert captured["client"] is redis.cache_redis_client
