"""What an API-key request may carry: the id's range, and text a database can store."""

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

SURROGATE = "\\ud800"


async def _create(auth_client: AsyncClient, body: str) -> Any:
    return await auth_client.post("/api/v1/api-keys/", content=body, headers={"Content-Type": "application/json"})


async def test_a_key_id_beyond_the_column_is_refused(auth_client: AsyncClient):
    """An ``Integer`` column cannot hold it, and the database would refuse the query."""
    response = await auth_client.get("/api/v1/api-keys/3000000000")

    assert response.status_code == 422


async def test_the_largest_id_the_column_holds_is_a_lookup(auth_client: AsyncClient):
    response = await auth_client.get("/api/v1/api-keys/2147483647")

    assert response.status_code == 404


class TestTextTheDatabaseCannotStore:
    """A lone surrogate is refused wherever it sits, and never echoed back."""

    async def test_a_nested_value_on_create(self, auth_client: AsyncClient):
        response = await _create(auth_client, '{"name": "Nested", "permissions": {"a": "' + SURROGATE + '"}}')

        assert response.status_code == 422
        assert "ud800" not in response.text

    async def test_a_nested_key_on_create(self, auth_client: AsyncClient):
        response = await _create(auth_client, '{"name": "Nested Key", "key_metadata": {"' + SURROGATE + '": "team"}}')

        assert response.status_code == 422

    async def test_a_nested_value_on_an_update(self, auth_client: AsyncClient):
        created = await auth_client.post("/api/v1/api-keys/", json={"name": "Updatable"})

        response = await auth_client.patch(
            f"/api/v1/api-keys/{created.json()['id']}",
            content='{"usage_limits": {"x": "' + SURROGATE + '"}}',
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    async def test_a_nested_key_on_an_update(self, auth_client: AsyncClient):
        created = await auth_client.post("/api/v1/api-keys/", json={"name": "Updatable Key"})

        response = await auth_client.patch(
            f"/api/v1/api-keys/{created.json()['id']}",
            content='{"key_metadata": {"' + SURROGATE + '": "team"}}',
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    async def test_text_a_database_can_store_is_accepted(self, auth_client: AsyncClient):
        response = await _create(auth_client, '{"name": "Fine", "key_metadata": {"team": "platform \\ud83d\\ude00"}}')

        assert response.status_code == 201
        assert response.json()["name"] == "Fine"
