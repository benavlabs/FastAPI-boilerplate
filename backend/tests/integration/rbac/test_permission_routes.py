"""Reading the permissions the project has, and the ones the caller holds."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.permissions import all_permissions, permission_groups
from tests.integration.rbac.test_user_permissions import _grant, _login

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]


async def test_the_listing_offers_every_registered_permission(client: AsyncClient, test_user: dict):
    """A role may carry nothing else, so this is what a UI building one may offer."""
    csrf = await _login(client, test_user)

    response = await client.get("/api/v1/permissions", headers={"X-CSRF-Token": csrf})

    assert response.status_code == 200
    listed = response.json()["permissions"]
    assert listed == {resource: list(names) for resource, names in sorted(permission_groups().items())}
    assert {name for names in listed.values() for name in names} == set(all_permissions())


async def test_the_listing_needs_a_session(client: AsyncClient):
    assert (await client.get("/api/v1/permissions")).status_code == 401


async def test_a_caller_with_no_role_holds_nothing(client: AsyncClient, test_user: dict):
    csrf = await _login(client, test_user)

    response = await client.get("/api/v1/permissions/me", headers={"X-CSRF-Token": csrf})

    assert response.status_code == 200
    assert response.json() == {"permissions": []}


async def test_a_caller_holds_what_their_role_carries(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    await _grant(db_session, test_user["id"], "editor", "user.update")
    csrf = await _login(client, test_user)

    response = await client.get("/api/v1/permissions/me", headers={"X-CSRF-Token": csrf})

    assert response.json() == {"permissions": ["user.update"]}


async def test_a_superuser_holds_every_registered_permission(client: AsyncClient, test_superuser: dict):
    csrf = await _login(client, test_superuser)

    response = await client.get("/api/v1/permissions/me", headers={"X-CSRF-Token": csrf})

    assert response.json() == {"permissions": sorted(all_permissions())}


async def test_the_callers_own_permissions_need_a_session(client: AsyncClient):
    assert (await client.get("/api/v1/permissions/me")).status_code == 401
