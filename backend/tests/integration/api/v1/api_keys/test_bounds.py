"""What an API-key request may carry: the id's range, and text a database can store."""

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

SURROGATE = "\\ud800"
NUL = "\\u0000"


def _nested(levels: int) -> str:
    """A ``key_metadata`` value nested ``levels`` deep, as a client would send it."""
    return '{"a": ' * levels + "1" + "}" * levels


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
        response = await _create(auth_client, '{"name": "Nested", "usage_limits": {"a": "' + SURROGATE + '"}}')

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

    async def test_a_nul_in_the_name_on_create(self, auth_client: AsyncClient):
        """It encodes, and Postgres then refuses the whole statement carrying it."""
        response = await _create(auth_client, '{"name": "a' + NUL + 'b"}')

        assert response.status_code == 422

    async def test_a_nul_nested_in_an_update(self, auth_client: AsyncClient):
        created = await auth_client.post("/api/v1/api-keys/", json={"name": "Updatable NUL"})

        response = await auth_client.patch(
            f"/api/v1/api-keys/{created.json()['id']}",
            content='{"key_metadata": {"team": "a' + NUL + 'b"}}',
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    async def test_text_a_database_can_store_is_accepted(self, auth_client: AsyncClient):
        response = await _create(auth_client, '{"name": "Fine", "key_metadata": {"team": "platform \\ud83d\\ude00"}}')

        assert response.status_code == 201
        assert response.json()["name"] == "Fine"


class TestMetadataTooLargeToStore:
    """``key_metadata`` is the client's to shape, so its depth and its size are capped."""

    async def test_a_value_nested_past_the_cap_on_create(self, auth_client: AsyncClient):
        response = await _create(auth_client, '{"name": "Deep", "key_metadata": ' + _nested(17) + "}")

        assert response.status_code == 422

    async def test_a_value_nested_deep_enough_to_exhaust_the_stack(self, auth_client: AsyncClient):
        """The depth is read before anything serializes it, or this raises where nothing refuses."""
        response = await _create(auth_client, '{"name": "Deeper", "key_metadata": ' + _nested(300) + "}")

        assert response.status_code == 422
        assert (await auth_client.get("/api/v1/api-keys/")).status_code == 200

    async def test_a_value_too_large_to_store_on_create(self, auth_client: AsyncClient):
        response = await _create(auth_client, '{"name": "Big", "key_metadata": {"a": "' + "x" * 9000 + '"}}')

        assert response.status_code == 422

    async def test_a_value_nested_past_the_cap_on_an_update(self, auth_client: AsyncClient):
        created = await _create(auth_client, '{"name": "Patched"}')
        assert created.status_code == 201

        response = await auth_client.patch(
            f"/api/v1/api-keys/{created.json()['id']}",
            content='{"key_metadata": ' + _nested(17) + "}",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    async def test_non_ascii_text_under_the_cap_is_accepted(self, auth_client: AsyncClient):
        """Counted escaped, these 3,000 characters read as 18,009 bytes and would be refused."""
        response = await _create(auth_client, '{"name": "Accented", "key_metadata": {"a": "' + "é" * 3000 + '"}}')

        assert response.status_code == 201

    async def test_metadata_the_project_stores_is_accepted_and_listable(self, auth_client: AsyncClient):
        """The control: what the caps allow is written and read back."""
        response = await _create(auth_client, '{"name": "Held", "key_metadata": ' + _nested(16) + "}")

        assert response.status_code == 201
        listed = await auth_client.get("/api/v1/api-keys/")
        assert listed.status_code == 200
        assert [entry["name"] for entry in listed.json()["data"]] == ["Held"]
