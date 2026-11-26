"""The cache's Redis speaks TLS when ``CACHE_REDIS_SSL`` says so."""

import pytest
from redis.asyncio.connection import Connection, SSLConnection

from src.infrastructure.cache import initialize
from src.infrastructure.cache.backends.redis import RedisBackend, RedisSettings
from src.infrastructure.cache.provider import cache_provider
from tests.fixtures.redis_tls import connection_in_a_fresh_process, spoken


@pytest.mark.parametrize(("ssl", "connection"), [(True, SSLConnection), (False, Connection)])
def test_the_cache_backend_builds_its_own_client_over_tls_when_asked(ssl: bool, connection: type):
    backend = RedisBackend(settings=RedisSettings(ssl=ssl))

    assert backend.client.connection_pool.connection_class is connection


@pytest.mark.parametrize("ssl", [True, False])
def test_the_cache_client_and_its_reported_target_speak_tls_when_the_setting_says(ssl: bool):
    shown = connection_in_a_fresh_process(
        {"CACHE_BACKEND": "redis", "CACHE_REDIS_SSL": str(ssl).lower()},
        "from src.infrastructure.cache.client import cache_redis_client as client; "
        "from src.infrastructure.cache.health import cache_target as target",
        "client.connection_pool.connection_class.__name__, target().split(':')[0]",
    )

    assert shown == spoken(ssl)


@pytest.mark.parametrize("ssl", [True, False])
async def test_the_registered_cache_backend_describes_the_connection_it_runs_on(ssl: bool, monkeypatch):
    """It runs on the shared client, so its settings are all that says what that client speaks."""
    settings = initialize.get_settings()
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_BACKEND", "redis")
    monkeypatch.setattr(settings, "CACHE_REDIS_SSL", ssl)
    monkeypatch.setattr(cache_provider, "_backends", {})
    monkeypatch.setattr(cache_provider, "_default_backend", None)

    await initialize.initialize_cache()
    backend = cache_provider.get_backend("redis")

    assert isinstance(backend, RedisBackend)
    assert backend.settings.ssl is ssl
