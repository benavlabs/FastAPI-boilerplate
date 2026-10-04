"""Read routes for API keys rely on the global domain-error handlers.

These pin the generic 404 and 403 bodies (no raw exception text, no echo of the
identifier) that the route modules previously produced themselves.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.dependencies import get_current_user
from src.interfaces.main import app
from src.modules.api_keys.models import APIKey

pytestmark = pytest.mark.asyncio


async def test_a_missing_api_key_returns_the_generic_not_found(auth_client: AsyncClient):
    response = await auth_client.get("/api/v1/api-keys/999999")

    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "The requested resource was not found."
    assert body["support_id"]


async def test_another_users_api_key_is_forbidden_generically(auth_client: AsyncClient, test_user_2: dict):
    created = await auth_client.post("/api/v1/api-keys/", json={"name": "Cross User Key"})
    assert created.status_code == 201
    key_id = created.json()["id"]

    app.dependency_overrides[get_current_user] = lambda: test_user_2
    response = await auth_client.get(f"/api/v1/api-keys/{key_id}")

    assert response.status_code == 403
    body = response.json()
    assert body["detail"] == "You don't have permission for this action."
    assert body["support_id"]
    assert "Cross User Key" not in response.text


async def test_the_usage_listing_is_capped_like_every_other(auth_client: AsyncClient):
    """It used to allow a thousand rows per page."""
    created = await auth_client.post("/api/v1/api-keys/", json={"name": "Usage Cap"})
    key_id = created.json()["id"]

    over = await auth_client.get(f"/api/v1/api-keys/{key_id}/usage", params={"items_per_page": 1000})
    allowed = await auth_client.get(f"/api/v1/api-keys/{key_id}/usage", params={"items_per_page": 100})

    assert over.status_code == 422
    assert allowed.status_code == 200


async def test_a_stored_name_the_input_rules_would_refuse_is_still_listed(auth_client: AsyncClient, db_session: AsyncSession):
    """The read schema enforced the create rules, so such a row answered 500."""
    created = await auth_client.post("/api/v1/api-keys/", json={"name": "Listed Key"})
    await db_session.execute(update(APIKey).where(APIKey.id == created.json()["id"]).values(name=""))

    listing = await auth_client.get("/api/v1/api-keys/")

    assert listing.status_code == 200
    assert listing.json()["data"][0]["name"] == ""
