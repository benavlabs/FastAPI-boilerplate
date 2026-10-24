"""A key is scoped by registry permission names, the same vocabulary a role carries.

The client here is a superuser's session, which holds every registered permission: a key's
scope may name no permission its creator lacks, and that rule has its own tests.
"""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

import scripts.cleanup_api_key_json as cleanup_script
from scripts.cleanup_api_key_json import cleanup_api_key_json
from src.infrastructure.permissions import all_permissions
from src.modules.api_keys.models import APIKey
from src.modules.common.constants import SUPPORT_ID_LENGTH

INVALID_REQUEST = "Invalid request. Please check your input and try again."
UNKNOWN = "widget.explode"

pytestmark = pytest.mark.asyncio


async def _create(client: AsyncClient, **body) -> dict[str, Any]:
    response = await client.post("/api/v1/api-keys/", json={"name": "Scoped Key", **body})
    assert response.status_code == 201, response.text

    created: dict[str, Any] = response.json()

    return created


async def test_a_key_is_created_with_the_names_it_is_scoped_to(superuser_auth_client: AsyncClient):
    created = await _create(superuser_auth_client, permissions=["user.update", "user.read"])

    assert created["permissions"] == ["user.read", "user.update"]

    read = await superuser_auth_client.get(f"/api/v1/api-keys/{created['id']}")
    assert read.json()["permissions"] == ["user.read", "user.update"]


async def test_a_name_the_registry_does_not_know_is_refused_on_create(superuser_auth_client: AsyncClient):
    """The refusal carries the generic body, so it doesn't echo what was sent."""
    response = await superuser_auth_client.post("/api/v1/api-keys/", json={"name": "Bad Scope", "permissions": [UNKNOWN]})

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == INVALID_REQUEST
    assert len(body["support_id"]) == SUPPORT_ID_LENGTH
    assert UNKNOWN not in str(body)


async def test_a_name_the_registry_does_not_know_is_refused_on_an_update(superuser_auth_client: AsyncClient):
    created = await _create(superuser_auth_client, permissions=["user.read"])

    response = await superuser_auth_client.patch(
        f"/api/v1/api-keys/{created['id']}", json={"permissions": ["user.read", UNKNOWN]}
    )
    read = await superuser_auth_client.get(f"/api/v1/api-keys/{created['id']}")

    assert response.status_code == 422
    assert UNKNOWN not in response.text
    assert read.json()["permissions"] == ["user.read"]


async def test_the_scope_an_older_version_stored_is_refused(superuser_auth_client: AsyncClient):
    """The object shape names nothing the registry knows, so it cannot be written."""
    response = await superuser_auth_client.post(
        "/api/v1/api-keys/", json={"name": "Legacy Scope", "permissions": {"conversations": ["read"]}}
    )

    assert response.status_code == 422


async def test_every_registered_name_can_scope_a_key(superuser_auth_client: AsyncClient):
    """The vocabulary is the registry's, so nothing a route gates on is unreachable."""
    created = await _create(superuser_auth_client, permissions=sorted(all_permissions()))

    assert created["permissions"] == sorted(all_permissions())


async def test_the_cleanup_makes_a_row_with_the_old_scope_readable_again(
    superuser_auth_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """A scope stored as an object answers 500 on every validated read until the repair runs."""
    created = await _create(superuser_auth_client, permissions=["user.read"])
    await db_session.execute(update(APIKey).where(APIKey.id == created["id"]).values(permissions={"conversations": ["read"]}))

    before = await superuser_auth_client.get("/api/v1/api-keys/")

    class _Session:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(cleanup_script, "local_session", _Session)
    await cleanup_api_key_json()

    after = await superuser_auth_client.get("/api/v1/api-keys/")

    assert before.status_code == 500
    assert after.status_code == 200
    assert after.json()["data"][0]["permissions"] == []
