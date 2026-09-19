"""Read routes for API keys rely on the global domain-error handlers.

These pin the generic 404 and 403 bodies (no raw exception text, no echo of the
identifier) that the route modules previously produced themselves.
"""

import pytest
from httpx import AsyncClient

from src.infrastructure.auth.dependencies import get_current_user
from src.interfaces.main import app

pytestmark = pytest.mark.asyncio


async def test_a_missing_api_key_returns_the_generic_not_found(auth_client: AsyncClient):
    response = await auth_client.get("/api/v1/api-keys/999999")

    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "The requested resource was not found."
    assert body["support_id"]
    assert "999999" not in body["detail"]


async def test_another_users_api_key_is_forbidden_generically(
    auth_client: AsyncClient, test_user: dict, test_user_2: dict
):
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
