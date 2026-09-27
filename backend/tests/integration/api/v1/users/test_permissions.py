"""RBAC on the user routes, exercised through a real login.

These sign in through ``/api/v1/auth/login`` instead of overriding the auth
dependencies, so the permission lookup runs against the same session the route
uses and a guard that only holds in a mock can't pass.
"""

from datetime import UTC, datetime

import pytest
from crudauth import Principal
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth import dependencies as deps
from src.infrastructure.database.session import async_session
from src.infrastructure.dependencies import CurrentPermissionsDep
from src.modules.role.models import Role, RolePermission, UserRole
from src.modules.user.models import User

pytestmark = pytest.mark.asyncio


async def _grant(db: AsyncSession, user_id: int, name: str, *permissions: str) -> Role:
    """Give a user a role carrying these permissions."""
    role = Role(name=name)
    db.add(role)
    await db.flush()
    db.add_all([RolePermission(role_id=role.id, permission_name=p) for p in permissions])
    db.add(UserRole(user_id=user_id, role_id=role.id))
    await db.commit()
    return role


async def _login(client: AsyncClient, user: dict) -> str:
    """Sign in for real and return the CSRF token for unsafe requests."""
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": user["username"], "password": user["password"]},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


# =============================================================================
# GET /users/ is behind user.read
# =============================================================================
async def test_listing_users_needs_the_read_permission(client: AsyncClient, test_user: dict):
    await _login(client, test_user)

    response = await client.get("/api/v1/users/")

    assert response.status_code == 403


async def test_a_role_granting_read_lists_users(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    await _grant(db_session, test_user["id"], "reader", "user.read")
    await _login(client, test_user)

    response = await client.get("/api/v1/users/")

    assert response.status_code == 200
    assert response.json()["data"]


async def test_a_superuser_lists_users_without_a_role(client: AsyncClient, test_superuser: dict):
    await _login(client, test_superuser)

    response = await client.get("/api/v1/users/")

    assert response.status_code == 200


async def test_listing_users_needs_authentication(client: AsyncClient):
    assert (await client.get("/api/v1/users/")).status_code == 401


# =============================================================================
# PATCH /users/{username}: what user.update may reach
# =============================================================================
async def test_an_update_holder_cannot_edit_a_superuser(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_superuser: dict
):
    """Editing a superuser's profile would be a route to taking the account over."""
    await _grant(db_session, test_user["id"], "editor", "user.update")
    csrf_token = await _login(client, test_user)

    response = await client.patch(
        f"/api/v1/users/{test_superuser['username']}",
        json={"name": "Pwned Name"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 403
    target = await db_session.get(User, test_superuser["id"])
    await db_session.refresh(target)
    assert target.name == test_superuser["name"]


async def test_an_update_holder_cannot_edit_someone_holding_more(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    await _grant(db_session, test_user["id"], "editor", "user.update")
    await _grant(db_session, test_user_2["id"], "deleter", "user.delete")
    csrf_token = await _login(client, test_user)

    response = await client.patch(
        f"/api/v1/users/{test_user_2['username']}",
        json={"name": "Pwned Name"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 403


async def test_an_update_holder_can_edit_a_weaker_user(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    await _grant(db_session, test_user["id"], "editor", "user.update")
    csrf_token = await _login(client, test_user)

    response = await client.patch(
        f"/api/v1/users/{test_user_2['username']}",
        json={"name": "Renamed User"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    target = await db_session.get(User, test_user_2["id"])
    await db_session.refresh(target)
    assert target.name == "Renamed User"


async def test_an_update_holder_cannot_change_another_users_email(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    """A verified provider email links a social login to an account, so this is superuser-only."""
    await _grant(db_session, test_user["id"], "editor", "user.update")
    csrf_token = await _login(client, test_user)

    response = await client.patch(
        f"/api/v1/users/{test_user_2['username']}",
        json={"email": "attacker@example.com"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 403
    target = await db_session.get(User, test_user_2["id"])
    await db_session.refresh(target)
    assert target.email == test_user_2["email"]


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
    owner = await db_session.get(User, test_user["id"])
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
    owner = await db_session.get(User, test_user["id"])
    await db_session.refresh(owner)
    assert owner.name == "My New Name"


async def test_a_superuser_can_change_another_users_email(
    client: AsyncClient, db_session: AsyncSession, test_superuser: dict, test_user_2: dict
):
    csrf_token = await _login(client, test_superuser)

    response = await client.patch(
        f"/api/v1/users/{test_user_2['username']}",
        json={"email": "moved@example.com"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200


# =============================================================================
# The permission lookup runs once per request
# =============================================================================
async def test_permissions_are_loaded_once_per_request(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch
):
    """``require_permissions`` and the route both ask for permissions; FastAPI caches the answer."""
    await _grant(db_session, test_user["id"], "reader", "user.read")
    await _login(client, test_user)

    calls: list[int] = []
    original = deps.load_permissions

    async def counting_load_permissions(db, user_id, *, is_superuser=False):
        calls.append(user_id)
        return await original(db, user_id, is_superuser=is_superuser)

    monkeypatch.setattr(deps, "load_permissions", counting_load_permissions)

    response = await client.get("/api/v1/users/")

    assert response.status_code == 200
    assert calls == [test_user["id"]]


async def test_one_request_resolves_permissions_once_however_many_ask(db_session: AsyncSession, test_user: dict, monkeypatch):
    """A guard and a handler that both need permissions share one lookup."""
    await _grant(db_session, test_user["id"], "reader", "user.read")

    calls: list[int] = []
    original = deps.load_permissions

    async def counting_load_permissions(db, user_id, *, is_superuser=False):
        calls.append(user_id)
        return await original(db, user_id, is_superuser=is_superuser)

    monkeypatch.setattr(deps, "load_permissions", counting_load_permissions)

    app = FastAPI()

    @app.get("/twice", dependencies=[deps.require_permissions("user.read")])
    async def twice(permissions: CurrentPermissionsDep) -> dict[str, int]:
        return {"held": len(permissions)}

    app.dependency_overrides[async_session] = lambda: db_session
    app.dependency_overrides[deps.get_current_principal] = lambda: Principal(user_id=test_user["id"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as local_client:
        response = await local_client.get("/twice")

    assert response.status_code == 200
    assert response.json() == {"held": 1}
    assert calls == [test_user["id"]]


async def test_a_stale_stored_permission_grants_nothing(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """A permission removed from the code is ignored rather than trusted."""
    role = Role(name="stale")
    db_session.add(role)
    await db_session.flush()
    db_session.add(UserRole(user_id=test_user["id"], role_id=role.id))
    await db_session.commit()
    await db_session.execute(
        RolePermission.__table__.insert().values(
            role_id=role.id,
            permission_name="user.retired",
            created_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    await _login(client, test_user)

    response = await client.get("/api/v1/users/")

    assert response.status_code == 403
    stored = await db_session.scalars(select(RolePermission.permission_name).where(RolePermission.role_id == role.id))
    assert list(stored) == ["user.retired"]
