"""Every API-key route answers through a schema, so no column leaks by default."""

import pytest
from httpx import AsyncClient

from src.modules.api_keys.schemas import APIKeyRead, APIKeyResponse, KeyUsageAnalytics, UserAPIKeySummary

pytestmark = pytest.mark.asyncio


async def test_creating_a_key_never_returns_its_hash(auth_client: AsyncClient):
    response = await auth_client.post("/api/v1/api-keys/", json={"name": "Shape Key"})

    assert response.status_code == 201
    body = response.json()
    assert "key_hash" not in body
    assert set(body) == set(APIKeyResponse.model_fields)
    assert body["api_key"].startswith("fai_")


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
