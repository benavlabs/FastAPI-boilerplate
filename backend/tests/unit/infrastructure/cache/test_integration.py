from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.infrastructure.cache.decorator import cache
from src.infrastructure.cache.provider import cache_provider


@pytest.fixture
def mock_redis_backend():
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock()
    redis_mock.delete = AsyncMock()
    redis_mock.delete_pattern = AsyncMock()
    return redis_mock


@pytest.fixture
def app(mock_redis_backend):
    with patch.object(cache_provider, "get_backend", return_value=mock_redis_backend):
        app = FastAPI()

        @app.get("/users/{user_id}")
        @cache(key_prefix="user", resource_id_name="user_id", per_caller=False)
        async def get_user(request: Request, user_id: int):
            return {"id": user_id, "name": f"User {user_id}"}

        @app.post("/users/{user_id}")
        @cache(key_prefix="user", resource_id_name="user_id", per_caller=False)
        async def update_user(request: Request, user_id: int, name: str | None = None):
            return {"id": user_id, "name": name, "updated": True}

        @app.put("/orgs/{org_id}/users/{user_id}")
        @cache(
            key_prefix="org_user",
            resource_id_name="user_id",
            to_invalidate_extra={"user": "user_id", "org": "org_id"},
            per_caller=False,
        )
        async def update_org_user(request: Request, org_id: int, user_id: int):
            return {"org_id": org_id, "user_id": user_id, "updated": True}

        yield app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_get_with_cache_miss(client, mock_redis_backend):
    mock_redis_backend.get.return_value = None
    response = client.get("/users/123")

    assert response.status_code == 200
    assert response.json() == {"id": 123, "name": "User 123"}

    mock_redis_backend.get.assert_called_once_with("user:123")
    mock_redis_backend.set.assert_called_once()
    assert mock_redis_backend.delete.call_count == 0


def test_get_with_cache_hit(client, mock_redis_backend):
    cached_data = {"id": 123, "name": "Cached User 123"}
    mock_redis_backend.get.return_value = cached_data

    response = client.get("/users/123")

    assert response.status_code == 200
    assert response.json() == cached_data

    mock_redis_backend.get.assert_called_once_with("user:123")
    mock_redis_backend.set.assert_not_called()


def test_post_invalidates_cache(client, mock_redis_backend):
    response = client.post("/users/123?name=Updated%20User")

    assert response.status_code == 200
    assert response.json() == {"id": 123, "name": "Updated User", "updated": True}

    mock_redis_backend.get.assert_not_called()
    mock_redis_backend.set.assert_not_called()
    mock_redis_backend.delete.assert_called_once_with("user:123")


def test_put_with_extra_invalidation(client, mock_redis_backend):
    response = client.put("/orgs/456/users/123")

    assert response.status_code == 200
    assert response.json() == {"org_id": 456, "user_id": 123, "updated": True}

    mock_redis_backend.delete.assert_any_call("org_user:123")
    mock_redis_backend.delete.assert_any_call("user:123")
    mock_redis_backend.delete.assert_any_call("org:456")
    assert mock_redis_backend.delete.call_count == 3
