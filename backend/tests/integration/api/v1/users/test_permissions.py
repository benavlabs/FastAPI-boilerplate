"""Permission checks on the user routes that hold whatever grants the wiring has.

These sign in through ``/api/v1/auth/login`` instead of overriding the auth
dependencies, so the checks run against the same session the route uses. Tests
that need a real grant live with the feature that issues one, in
``tests/integration/rbac/``.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth import authorization as authz
from src.modules.user.models import User

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]


async def _login(client: AsyncClient, user: dict) -> str:
    """Sign in for real and return the CSRF token for unsafe requests."""
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": user["username"], "password": user["password"]},
    )
    assert response.status_code == 200, response.text
    token: str = response.json()["csrf_token"]

    return token


async def test_listing_users_needs_the_read_permission(client: AsyncClient, test_user: dict):
    await _login(client, test_user)

    response = await client.get("/api/v1/users/")

    assert response.status_code == 403


async def test_a_superuser_lists_users_without_a_role(client: AsyncClient, test_superuser: dict):
    await _login(client, test_superuser)

    response = await client.get("/api/v1/users/")

    assert response.status_code == 200


async def test_listing_users_needs_authentication(client: AsyncClient):
    assert (await client.get("/api/v1/users/")).status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"google_id": "attacker-google-sub"},
        {"github_id": "attacker-github-id"},
        {"oauth_provider": "google"},
        {"email_verified": True},
        {"oauth_updated_at": "2026-01-01T00:00:00Z"},
    ],
)
async def test_the_public_endpoint_refuses_the_oauth_fields(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, payload: dict
):
    """Setting an OAuth identifier decides who a provider login resolves to."""
    csrf_token = await _login(client, test_user)

    response = await client.patch(
        f"/api/v1/users/{test_user['username']}",
        json=payload,
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422
    owner = await db_session.get_one(User, test_user["id"])
    await db_session.refresh(owner)
    assert owner.google_id is None
    assert owner.email_verified is False


async def test_a_user_still_edits_their_own_profile(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    csrf_token = await _login(client, test_user)

    response = await client.patch(
        f"/api/v1/users/{test_user['username']}",
        json={"name": "My New Name"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    owner = await db_session.get_one(User, test_user["id"])
    await db_session.refresh(owner)
    assert owner.name == "My New Name"


async def test_not_even_a_superuser_changes_an_address_through_this_route(
    client: AsyncClient, db_session: AsyncSession, test_superuser: dict, test_user_2: dict
):
    """The address moves through the confirmed flow; the admin panel is the other way in."""
    csrf_token = await _login(client, test_superuser)

    response = await client.patch(
        f"/api/v1/users/{test_user_2['username']}",
        json={"email": "moved@example.com"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


async def test_a_contributed_source_lets_a_holder_through(client: AsyncClient, test_user: dict, monkeypatch):
    """Whatever feature answers, holding the permission is what opens the route."""

    async def source(db, user_id):
        return {"user.read"}

    monkeypatch.setattr(authz, "PERMISSION_SOURCES", (source,))
    await _login(client, test_user)

    assert (await client.get("/api/v1/users/")).status_code == 200


async def test_without_a_source_a_non_superuser_is_refused(client: AsyncClient, test_user: dict, monkeypatch):
    """A project that contributes no source falls back to superuser-only checks."""
    monkeypatch.setattr(authz, "PERMISSION_SOURCES", ())
    await _login(client, test_user)

    assert (await client.get("/api/v1/users/")).status_code == 403


async def test_without_a_source_a_superuser_still_passes(client: AsyncClient, test_superuser: dict, monkeypatch):
    monkeypatch.setattr(authz, "PERMISSION_SOURCES", ())
    await _login(client, test_superuser)

    assert (await client.get("/api/v1/users/")).status_code == 200
