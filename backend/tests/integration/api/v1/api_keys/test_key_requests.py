"""A request authenticated by ``X-API-Key``: what it may reach, and what it may not."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.routes import SESSION_ONLY_PATHS
from src.interfaces.main import app
from src.modules.api_keys.models import APIKey
from src.modules.api_keys.schemas import APIKeyCreate
from src.modules.api_keys.service import APIKeyService
from src.modules.api_keys.transport import API_KEY_HEADER
from src.modules.user.models import User
from tests.fixtures.accounts import reset_recovery_budgets

pytestmark = pytest.mark.asyncio

SESSION_ONLY_ROUTES = [
    ("POST", "/api/v1/auth/change-password", {"current_password": "Password123!", "new_password": "Password456!"}),
    ("POST", "/api/v1/auth/email/change-request", {"email": "moved@example.com", "current_password": "Password123!"}),
    ("POST", "/api/v1/auth/logout", None),
    ("POST", "/api/v1/auth/logout-all", None),
    ("GET", "/api/v1/api-keys/", None),
    ("POST", "/api/v1/api-keys/", {"name": "Minted By A Key"}),
    ("GET", "/api/v1/api-keys/summary/user", None),
    ("POST", "/api/v1/auth/csrf/refresh", None),
    ("GET", "/api/v1/auth/sessions", None),
    ("DELETE", "/api/v1/users/{username}", None),
]


async def _mint(db_session: AsyncSession, user_id: int, **fields: Any) -> dict[str, Any]:
    """A key row as the service writes it, with the raw key the caller presents."""
    minted: dict[str, Any] = await APIKeyService().create_api_key(
        user_id=user_id, key_data=APIKeyCreate(name="Request Key", **fields), db=db_session
    )

    return minted


@pytest.fixture
async def key(db_session: AsyncSession, test_user: dict) -> dict[str, Any]:
    return await _mint(db_session, test_user["id"])


def _with(key: dict[str, Any]) -> dict[str, str]:
    return {API_KEY_HEADER: key["api_key"]}


@pytest.fixture
async def signed_in(client: AsyncClient, test_user: dict, fresh_login_lockout) -> AsyncClient:
    """The same client with a real session on it, cookies and CSRF token included."""
    await reset_recovery_budgets(test_user["email"])
    response = await client.post(
        "/api/v1/auth/login", data={"username": test_user["username"], "password": test_user["password"]}
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]

    return client


async def test_a_key_cannot_close_the_account_that_issued_it(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, key: dict[str, Any]
):
    """A deactivated account would take its keys down with it, so a key must not do it."""
    response = await client.delete(f"/api/v1/users/{test_user['username']}", headers=_with(key))

    assert response.status_code == 401
    stored = await db_session.get_one(User, test_user["id"])
    await db_session.refresh(stored)
    assert stored.is_deleted is False


async def test_a_key_authenticates_a_protected_route_without_a_csrf_token(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, key: dict[str, Any]
):
    """CSRF guards a cookie the browser attaches by itself; a key is sent deliberately."""
    response = await client.patch(
        f"/api/v1/users/{test_user['username']}", json={"name": "Renamed By A Key"}, headers=_with(key)
    )

    assert response.status_code == 200, response.text
    stored = await db_session.get_one(User, test_user["id"])
    await db_session.refresh(stored)
    assert stored.name == "Renamed By A Key"


async def test_a_key_request_is_answered_without_a_cookie(client: AsyncClient, test_user: dict, key: dict[str, Any]):
    """Nothing about a key request is remembered in the client, so none of it is a session."""
    response = await client.get("/api/v1/auth/me", headers=_with(key))

    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    assert len(client.cookies) == 0


async def test_the_principal_a_key_resolves_names_its_owner_and_its_transport(
    client: AsyncClient, test_user: dict, key: dict[str, Any]
):
    response = await client.get("/api/v1/auth/me", headers=_with(key))

    body = response.json()
    assert body["user_id"] == test_user["id"]
    assert body["username"] == test_user["username"]
    assert body["via"] == "apikey"


async def test_a_session_wins_when_a_request_carries_both(signed_in: AsyncClient, key: dict[str, Any]):
    """The session transport is registered first, so a browser's stray key header changes nothing."""
    response = await signed_in.get("/api/v1/auth/me", headers=_with(key))

    assert response.json()["via"] == "session"


async def test_an_anonymous_route_reports_a_key_holder_as_authenticated(
    client: AsyncClient, test_user: dict, key: dict[str, Any]
):
    """The route reads a session out of the principal's metadata, and a key has none."""
    response = await client.get("/api/v1/auth/check-auth", headers=_with(key))

    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["user"]["username"] == test_user["username"]
    assert body["session"] == {"created_at": None, "last_activity": None}


async def test_every_reserved_path_is_a_route_that_exists():
    """A path the gate names and crudauth doesn't mount would gate nothing, quietly."""
    mounted = {route.path.removeprefix("/api/v1/auth") for route in app.routes if hasattr(route, "path")}

    assert set(SESSION_ONLY_PATHS) <= mounted


class TestAKeyThatMustNotAuthenticate:
    """Each one answers 401, and none of them falls through to anonymous."""

    async def test_a_malformed_key(self, client: AsyncClient, test_user: dict):
        response = await client.get("/api/v1/auth/me", headers={API_KEY_HEADER: "not-a-key"})

        assert response.status_code == 401

    async def test_a_key_that_matches_no_row(self, client: AsyncClient, test_user: dict, key: dict[str, Any]):
        presented = key["api_key"][:-4] + "beef"

        response = await client.get("/api/v1/auth/me", headers={API_KEY_HEADER: presented})

        assert response.status_code == 401

    async def test_a_revoked_key(self, client: AsyncClient, db_session: AsyncSession, test_user: dict, key: dict[str, Any]):
        await db_session.execute(update(APIKey).where(APIKey.id == key["id"]).values(is_active=False))
        await db_session.commit()

        response = await client.get("/api/v1/auth/me", headers=_with(key))

        assert response.status_code == 401

    async def test_an_expired_key(self, client: AsyncClient, db_session: AsyncSession, test_user: dict):
        expired = await _mint(db_session, test_user["id"], expires_at=datetime.now(UTC) + timedelta(seconds=1))
        await db_session.execute(
            update(APIKey).where(APIKey.id == expired["id"]).values(expires_at=datetime.now(UTC) - timedelta(days=1))
        )
        await db_session.commit()

        response = await client.get("/api/v1/auth/me", headers=_with(expired))

        assert response.status_code == 401

    async def test_a_key_whose_owner_a_soft_delete_took_out(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, key: dict[str, Any]
    ):
        await db_session.execute(update(User).where(User.id == test_user["id"]).values(is_deleted=True))
        await db_session.commit()

        response = await client.get("/api/v1/auth/me", headers=_with(key))

        assert response.status_code == 401

    async def test_a_route_that_answers_anonymous_callers_still_refuses_it(self, client: AsyncClient):
        """A credential that is present and wrong is an attack signal, not an absent one."""
        anonymous = await client.get("/api/v1/auth/check-auth")

        response = await client.get("/api/v1/auth/check-auth", headers={API_KEY_HEADER: "not-a-key"})

        assert anonymous.status_code == 200
        assert anonymous.json()["authenticated"] is False
        assert response.status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), SESSION_ONLY_ROUTES)
async def test_a_session_only_route_refuses_a_key(
    client: AsyncClient, test_user: dict, key: dict[str, Any], method: str, path: str, body: dict[str, Any] | None
):
    """Changing a password, moving an address, closing an account, ending a session and managing keys."""
    response = await client.request(method, path.format(**test_user), json=body, headers=_with(key))

    assert response.status_code == 401, response.text


@pytest.mark.parametrize(("method", "path", "body"), SESSION_ONLY_ROUTES)
async def test_a_session_only_route_answers_a_real_session(
    signed_in: AsyncClient, test_user: dict, method: str, path: str, body: dict[str, Any] | None
):
    """The control: the gate is the credential, not the route."""
    response = await signed_in.request(method, path.format(**test_user), json=body)

    assert response.status_code != 401, response.text
