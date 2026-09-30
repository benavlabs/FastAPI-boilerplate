"""An explicit ``null`` for a column the row requires is refused, not stored."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("field", ["name", "is_active", "permissions", "usage_limits"])
async def test_an_explicit_null_is_refused(auth_client: AsyncClient, field: str):
    created = await auth_client.post("/api/v1/api-keys/", json={"name": "Null Key"})
    assert created.status_code == 201

    response = await auth_client.patch(f"/api/v1/api-keys/{created.json()['id']}", json={field: None})

    assert response.status_code == 422


async def test_the_listing_still_works_after_a_refused_null(auth_client: AsyncClient):
    """A stored JSON null used to make the owner's listing answer 500."""
    created = await auth_client.post("/api/v1/api-keys/", json={"name": "Listing Key"})
    assert created.status_code == 201

    refused = await auth_client.patch(f"/api/v1/api-keys/{created.json()['id']}", json={"permissions": None})
    listing = await auth_client.get("/api/v1/api-keys/")

    assert refused.status_code == 422
    assert listing.status_code == 200
    assert listing.json()["data"][0]["permissions"] == {}


async def test_revocation_stays_one_way_against_a_null(auth_client: AsyncClient):
    created = await auth_client.post("/api/v1/api-keys/", json={"name": "Revoked Key"})
    key_id = created.json()["id"]
    assert (await auth_client.delete(f"/api/v1/api-keys/{key_id}")).status_code == 204

    response = await auth_client.patch(f"/api/v1/api-keys/{key_id}", json={"is_active": None})

    assert response.status_code == 422
