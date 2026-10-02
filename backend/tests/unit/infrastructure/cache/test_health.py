"""The cache readiness check really pings the cache, and skips what isn't configured."""

import asyncio
import gc

import anyio
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


async def _memcached_server(reply: bytes | None) -> tuple[asyncio.Server, int, asyncio.Event]:
    """A server on a free port that answers ``reply``, or accepts and never answers."""
    saw_eof = asyncio.Event()

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()
        if reply is not None:
            writer.write(reply)
            await writer.drain()
        await reader.read()
        saw_eof.set()
        writer.close()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)

    return server, server.sockets[0].getsockname()[1], saw_eof


UNREACHABLE_HOST = "10.255.255.1"


async def test_a_memory_cache_names_no_server(monkeypatch):
    """Nothing is reachable or unreachable when the cache lives in the process."""
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_BACKEND", CacheBackend.MEMORY.value)

    await health.cache_is_reachable()

    assert health.cache_target() is None


async def test_a_blackholed_memcached_times_out(monkeypatch):
    """A real socket to an address nothing answers on, bounded as the probe bounds it."""
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_BACKEND", CacheBackend.MEMCACHED.value)
    monkeypatch.setattr(settings, "CACHE_MEMCACHED_HOST", UNREACHABLE_HOST)

    with pytest.raises(TimeoutError), anyio.fail_after(0.3):
        await health.cache_is_reachable()


@pytest.fixture
def memcached_settings(monkeypatch):
    """A memcached cache, with the host and port left to each test."""
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_BACKEND", CacheBackend.MEMCACHED.value)
    monkeypatch.setattr(settings, "CACHE_MEMCACHED_HOST", "127.0.0.1")

    return monkeypatch


async def test_a_memcached_that_answers_its_version_is_reachable(memcached_settings):
    server, port, _ = await _memcached_server(b"VERSION 1.6.0\r\n")
    memcached_settings.setattr(settings, "CACHE_MEMCACHED_PORT", port)

    try:
        await health.cache_is_reachable()
    finally:
        server.close()
        await server.wait_closed()


async def test_a_server_that_answers_something_else_is_not_memcached(memcached_settings):
    server, port, _ = await _memcached_server(b"ERROR\r\n")
    memcached_settings.setattr(settings, "CACHE_MEMCACHED_PORT", port)

    try:
        with pytest.raises(ConnectionError):
            await health.cache_is_reachable()
    finally:
        server.close()
        await server.wait_closed()


async def test_a_server_that_never_answers_leaves_no_socket_open(memcached_settings):
    """The probe's timeout cancels the read, and the check still closes its socket."""
    server, port, saw_eof = await _memcached_server(None)
    memcached_settings.setattr(settings, "CACHE_MEMCACHED_PORT", port)

    try:
        with pytest.raises(TimeoutError), anyio.fail_after(0.2):
            await health.cache_is_reachable()

        with anyio.fail_after(2):
            await saw_eof.wait()
    finally:
        server.close()
        await server.wait_closed()

    gc.collect()
