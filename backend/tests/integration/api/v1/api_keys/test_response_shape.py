"""Every API-key route answers through a schema, so no column leaks by default."""

import pytest
from httpx import AsyncClient

from src.modules.api_keys.schemas import APIKeyRead, KeyUsageAnalytics, UserAPIKeySummary

pytestmark = pytest.mark.asyncio

WITHHELD_FROM_THE_CREATE_RESPONSE = {"key_metadata", "last_used_ip"}


async def test_creating_a_key_returns_the_key_and_nothing_stored_about_its_use(auth_client: AsyncClient):
    response = await auth_client.post(
        "/api/v1/api-keys/",
        json={"name": "Shape Key", "key_metadata": {"team": "platform"}},
    )

    assert response.status_code == 201
    body = response.json()
    assert "key_hash" not in body
    assert "last_used_ip" not in body
    assert "key_metadata" not in body
    assert body["api_key"].startswith("fai_")


async def test_the_create_response_is_the_read_schema_minus_those_two(auth_client: AsyncClient):
    """A field added to the read schema reaches the create response too."""
    response = await auth_client.post("/api/v1/api-keys/", json={"name": "Fields Key"})

    body = response.json()

    assert set(body) == (set(APIKeyRead.model_fields) | {"api_key"}) - WITHHELD_FROM_THE_CREATE_RESPONSE
    assert body["name"] == "Fields Key"
    assert body["api_key"].startswith(f"fai_{body['key_prefix']}_")
    assert body["is_active"] is True
    assert body["permissions"] == {}
    assert body["usage_limits"] == {}
    assert body["expires_at"] is None


async def test_reading_and_updating_answer_the_read_schema(auth_client: AsyncClient):
    created = await auth_client.post("/api/v1/api-keys/", json={"name": "Read Shape"})
    key_id = created.json()["id"]

    read = await auth_client.get(f"/api/v1/api-keys/{key_id}")
    updated = await auth_client.patch(f"/api/v1/api-keys/{key_id}", json={"name": "Renamed"})

    assert set(read.json()) == set(APIKeyRead.model_fields)
    assert set(updated.json()) == set(APIKeyRead.model_fields)
    assert updated.json()["name"] == "Renamed"


async def test_analytics_and_the_summary_answer_their_schemas(auth_client: AsyncClient):
    created = await auth_client.post("/api/v1/api-keys/", json={"name": "Analytics Shape"})
    key_id = created.json()["id"]

    analytics = await auth_client.get(f"/api/v1/api-keys/{key_id}/analytics")
    summary = await auth_client.get("/api/v1/api-keys/summary/user")

    assert set(analytics.json()) == set(KeyUsageAnalytics.model_fields)
    assert set(summary.json()) == set(UserAPIKeySummary.model_fields)
    assert set(summary.json()["keys"][0]) == set(APIKeyRead.model_fields)
