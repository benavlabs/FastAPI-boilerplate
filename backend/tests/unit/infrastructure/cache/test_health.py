"""The cache readiness check really pings the cache, and skips what isn't configured."""

import pytest

from src.infrastructure.cache import health
from src.infrastructure.config.enums import CacheBackend
from src.infrastructure.config.settings import settings

pytestmark = pytest.mark.asyncio


async def test_a_disabled_cache_is_nothing_to_report(monkeypatch):
    monkeypatch.setattr(settings, "CACHE_ENABLED", False)

    async def refuse() -> bool:
        raise AssertionError("a disabled cache must not be pinged")

    monkeypatch.setattr(health.cache_redis_client, "ping", refuse)

    await health.cache_is_reachable()

    assert health.cache_target() is None


async def test_a_redis_cache_is_pinged(monkeypatch):
    pings: list[bool] = []

    async def ping() -> bool:
        pings.append(True)
        return True

    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_BACKEND", CacheBackend.REDIS.value)
    monkeypatch.setattr(health.cache_redis_client, "ping", ping)

    await health.cache_is_reachable()

    assert pings == [True]
    target = health.cache_target()
    assert target is not None and target.startswith("redis://")


async def test_an_unreachable_redis_cache_raises(monkeypatch):
    async def refuse() -> bool:
        raise ConnectionRefusedError("nothing listening")

    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_BACKEND", CacheBackend.REDIS.value)
    monkeypatch.setattr(health.cache_redis_client, "ping", refuse)

    with pytest.raises(ConnectionRefusedError):
        await health.cache_is_reachable()


async def test_a_memcached_cache_is_asked_for_its_version(monkeypatch):
    """Memcached used to report ready without being asked anything."""
    versions: list[bool] = []

    class _Client:
        async def version(self) -> bytes:
            versions.append(True)
            return b"1.6.0"

    class _Backend:
        client = _Client()

    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_BACKEND", CacheBackend.MEMCACHED.value)
    monkeypatch.setattr(health.cache_provider, "get_backend", lambda name: _Backend())

    await health.cache_is_reachable()

    assert versions == [True]
    target = health.cache_target()
    assert target is not None and target.startswith("memcached://")
