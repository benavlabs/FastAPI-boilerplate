"""The memcached backend, which ships only with `cache.backend=memcached`, the choice that installs
aiomcache for it."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.cache import initialize
from src.infrastructure.cache.backends.memcached import MemcachedBackend, MemcachedSettings
from src.infrastructure.cache.exceptions import PatternMatchingNotSupportedError
from src.infrastructure.config.settings import settings


@pytest.fixture
def mock_memcached():
    memcached_mock = MagicMock()
    memcached_mock.get = AsyncMock()
    memcached_mock.set = AsyncMock()
    memcached_mock.delete = AsyncMock()
    return memcached_mock


@pytest.fixture
def memcached_backend(mock_memcached):
    with patch(
        "src.infrastructure.cache.backends.memcached.aiomcache.Client",
        return_value=mock_memcached,
    ):
        settings = MemcachedSettings(host="localhost", port=11211)
        backend = MemcachedBackend(settings=settings)
        backend.client = mock_memcached
        return backend


@pytest.mark.asyncio
async def test_get_existing_key(memcached_backend, mock_memcached):
    test_data = {"key": "value"}
    serialized_data = json.dumps(test_data).encode()
    mock_memcached.get.return_value = serialized_data

    result = await memcached_backend.get("test_key")

    assert result == test_data
    mock_memcached.get.assert_called_once_with(b"test_key")


@pytest.mark.asyncio
async def test_get_nonexistent_key(memcached_backend, mock_memcached):
    mock_memcached.get.return_value = None

    result = await memcached_backend.get("test_key")

    assert result is None
    mock_memcached.get.assert_called_once_with(b"test_key")


@pytest.mark.asyncio
async def test_set_key(memcached_backend, mock_memcached):
    test_data = {"key": "value"}

    await memcached_backend.set("test_key", test_data, 3600)

    mock_memcached.set.assert_called_once_with(b"test_key", json.dumps(test_data).encode(), exptime=3600)


@pytest.mark.asyncio
async def test_delete_key(memcached_backend, mock_memcached):
    await memcached_backend.delete("test_key")

    mock_memcached.delete.assert_called_once_with(b"test_key")


@pytest.mark.asyncio
async def test_delete_pattern_raises_error(memcached_backend):
    with pytest.raises(PatternMatchingNotSupportedError):
        await memcached_backend.delete_pattern("test_*")


async def test_a_memcached_cache_registers_the_backend_initialize_loads_by_name(monkeypatch, mock_memcached):
    """`initialize_cache` loads this module by name, since nothing imports it outright, and registers
    the backend it finds there."""
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_BACKEND", "memcached")
    registered: dict[str, object] = {}
    monkeypatch.setattr(
        initialize.cache_provider, "register_backend", lambda name, backend, default: registered.update({name: backend})
    )

    with patch("src.infrastructure.cache.backends.memcached.aiomcache.Client", return_value=mock_memcached):
        await initialize.initialize_cache()

    assert isinstance(registered["memcached"], MemcachedBackend)
