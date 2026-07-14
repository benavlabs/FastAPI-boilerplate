import json
from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.cache.backends.redis import RedisBackend, RedisSettings


@pytest.fixture
def mock_redis():
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock()
    redis_mock.set = AsyncMock()
    redis_mock.delete = AsyncMock()
    redis_mock.keys = AsyncMock()
    redis_mock.scan = AsyncMock()
    return redis_mock


@pytest.fixture
def redis_backend(mock_redis):
    with patch("src.infrastructure.cache.backends.redis.Redis", return_value=mock_redis):
        settings = RedisSettings(host="localhost", port=6379, password=None, db=0)
        backend = RedisBackend(settings=settings)
        backend.client = mock_redis
        return backend


@pytest.mark.asyncio
async def test_get_existing_key(redis_backend, mock_redis):
    test_data = {"key": "value"}
    serialized_data = json.dumps(test_data).encode()
    mock_redis.get.return_value = serialized_data

    result = await redis_backend.get("test_key")

    assert result == test_data
    mock_redis.get.assert_called_once_with("test_key")


@pytest.mark.asyncio
async def test_get_nonexistent_key(redis_backend, mock_redis):
    mock_redis.get.return_value = None

    result = await redis_backend.get("test_key")

    assert result is None
    mock_redis.get.assert_called_once_with("test_key")


@pytest.mark.asyncio
async def test_set_key(redis_backend, mock_redis):
    test_data = {"key": "value"}

    await redis_backend.set("test_key", test_data, 3600)

    mock_redis.set.assert_called_once_with("test_key", json.dumps(test_data).encode(), ex=3600)


@pytest.mark.asyncio
async def test_delete_key(redis_backend, mock_redis):
    await redis_backend.delete("test_key")

    mock_redis.delete.assert_called_once_with("test_key")


@pytest.mark.asyncio
async def test_delete_pattern(redis_backend, mock_redis):
    mock_redis.scan.return_value = (0, [b"key1", b"key2", b"key3"])

    await redis_backend.delete_pattern("test_")

    mock_redis.scan.assert_called_once_with(cursor=0, match="test_*", count=100)

    mock_redis.delete.assert_called_once_with(b"key1", b"key2", b"key3")


@pytest.mark.asyncio
async def test_delete_pattern_pages_cursor(redis_backend, mock_redis):
    """delete_pattern pages the SCAN cursor to completion, not just the first batch.

    Regression: the old implementation ran a single SCAN and silently left matches
    beyond the first window undeleted.
    """
    mock_redis.scan.side_effect = [(5, [b"a1", b"a2"]), (0, [b"a3"])]

    await redis_backend.delete_pattern("a")

    assert mock_redis.scan.await_count == 2
    # the second scan resumes from the cursor the first one returned
    assert mock_redis.scan.await_args_list[1].kwargs["cursor"] == 5
    deleted = [k for call in mock_redis.delete.await_args_list for k in call.args]
    assert deleted == [b"a1", b"a2", b"a3"]
