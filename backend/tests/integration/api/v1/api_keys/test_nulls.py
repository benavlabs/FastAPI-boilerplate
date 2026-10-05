"""An explicit ``null`` for a column the row requires is refused, not stored."""

import pytest
from httpx import AsyncClient
from sqlalchemy import JSON, update
from sqlalchemy.ext.asyncio import AsyncSession

import scripts.cleanup_api_key_json as cleanup_script
from scripts.cleanup_api_key_json import cleanup_api_key_json
from src.modules.api_keys.models import APIKey
from src.modules.common.constants import SUPPORT_ID_LENGTH

INVALID_REQUEST = "Invalid request. Please check your input and try again."

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("field", "accepted"),
    [("name", "Renamed"), ("is_active", False), ("permissions", {}), ("usage_limits", {})],
)
async def test_an_explicit_null_is_refused(auth_client: AsyncClient, field: str, accepted):
    """Every 422 carries the same generic body, so the control says the null caused this one."""
    created = await auth_client.post("/api/v1/api-keys/", json={"name": "Null Key"})
    assert created.status_code == 201
    key_id = created.json()["id"]

    response = await auth_client.patch(f"/api/v1/api-keys/{key_id}", json={field: None})
    control = await auth_client.patch(f"/api/v1/api-keys/{key_id}", json={field: accepted})

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == INVALID_REQUEST
    assert len(body["support_id"]) == SUPPORT_ID_LENGTH
    assert field not in str(body)
    assert control.status_code == 200, control.text


async def test_the_listing_still_works_after_a_refused_null(auth_client: AsyncClient):
    """A stored JSON null used to make the owner's listing answer 500."""
    created = await auth_client.post("/api/v1/api-keys/", json={"name": "Listing Key"})
    assert created.status_code == 201

    refused = await auth_client.patch(f"/api/v1/api-keys/{created.json()['id']}", json={"permissions": None})
    listing = await auth_client.get("/api/v1/api-keys/")

    assert refused.status_code == 422
    assert refused.json()["detail"] == INVALID_REQUEST
    assert listing.status_code == 200
    assert listing.json()["data"][0]["permissions"] == {}


async def test_revocation_stays_one_way_against_a_null(auth_client: AsyncClient):
    created = await auth_client.post("/api/v1/api-keys/", json={"name": "Revoked Key"})
    key_id = created.json()["id"]
    assert (await auth_client.delete(f"/api/v1/api-keys/{key_id}")).status_code == 204

    response = await auth_client.patch(f"/api/v1/api-keys/{key_id}", json={"is_active": None})

    assert response.status_code == 422
    assert response.json()["detail"] == INVALID_REQUEST
    assert (await auth_client.get(f"/api/v1/api-keys/{key_id}")).json()["is_active"] is False


async def test_the_cleanup_makes_a_legacy_null_row_readable_again(
    auth_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """A row stored before the null was refused answered 500 on every validated read."""
    created = await auth_client.post("/api/v1/api-keys/", json={"name": "Legacy Key"})
    key_id = created.json()["id"]
    await db_session.execute(update(APIKey).where(APIKey.id == key_id).values(permissions=JSON.NULL, usage_limits=JSON.NULL))

    before = await auth_client.get("/api/v1/api-keys/")

    class _Session:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(cleanup_script, "local_session", _Session)
    await cleanup_api_key_json()

    after = await auth_client.get("/api/v1/api-keys/")

    assert before.status_code == 500
    assert after.status_code == 200
    assert after.json()["data"][0]["permissions"] == {}
    assert after.json()["data"][0]["usage_limits"] == {}
