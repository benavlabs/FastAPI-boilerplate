"""The account routes crudauth ships, and the budget password guesses share."""

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from src.interfaces.main import app

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

NEW_PASSWORD = "An0therPassword!"


async def _login(client: AsyncClient, user: dict, password: str | None = None) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": user["username"], "password": password or user["password"]},
    )
    assert response.status_code == 200, response.text
    token: str = response.json()["csrf_token"]

    return token


async def _second_session(user: dict) -> tuple[AsyncClient, str]:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    csrf = await _login(client, user)

    return client, csrf


async def test_changing_the_password_replaces_the_one_that_logs_in(client: AsyncClient, test_user: dict):
    csrf = await _login(client, test_user)

    changed = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": test_user["password"], "new_password": NEW_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    client.cookies.clear()
    with_the_old = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )

    assert changed.status_code == 200
    assert with_the_old.status_code == 401
    await _login(client, test_user, NEW_PASSWORD)


async def test_changing_the_password_revokes_the_other_sessions(client: AsyncClient, test_user: dict):
    other, _ = await _second_session(test_user)
    csrf = await _login(client, test_user)

    assert (await other.get("/api/v1/users/me")).status_code == 200

    changed = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": test_user["password"], "new_password": NEW_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    with_the_other_session = await other.get("/api/v1/users/me")
    with_the_changing_session = await client.get("/api/v1/users/me")
    await other.aclose()

    assert changed.status_code == 200
    assert with_the_other_session.status_code == 401
    assert with_the_changing_session.status_code == 200


async def test_the_wrong_current_password_changes_nothing(client: AsyncClient, test_user: dict):
    csrf = await _login(client, test_user)

    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "NotTheOne123!", "new_password": NEW_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    client.cookies.clear()

    assert response.status_code == 401
    await _login(client, test_user)


async def test_a_new_password_that_breaks_the_policy_is_refused(client: AsyncClient, test_user: dict):
    csrf = await _login(client, test_user)

    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": test_user["password"], "new_password": "short"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
    assert test_user["password"] not in response.text


async def test_changing_a_password_needs_a_session(client: AsyncClient, test_user: dict):
    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": test_user["password"], "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 401


class TestTheChangePasswordBudget:
    """crudauth caps the guesses one account may make, successes included."""

    async def _change_password_with(self, client: AsyncClient, csrf: str, password: str) -> int:
        response = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": password, "new_password": NEW_PASSWORD},
            headers={"X-CSRF-Token": csrf},
        )

        return response.status_code

    async def test_the_sixth_wrong_guess_is_refused(self, client: AsyncClient, test_user: dict):
        csrf = await _login(client, test_user)

        refused = [await self._change_password_with(client, csrf, "WrongPassword1!") for _ in range(5)]
        sixth = await self._change_password_with(client, csrf, "WrongPassword1!")

        assert refused == [401, 401, 401, 401, 401]
        assert sixth == 429

    async def test_the_right_password_on_the_first_try_succeeds(self, client: AsyncClient, test_user: dict):
        csrf = await _login(client, test_user)

        assert await self._change_password_with(client, csrf, test_user["password"]) == 200


async def test_setting_a_password_is_not_a_route_this_app_exposes(client: AsyncClient, test_user: dict):
    csrf = await _login(client, test_user)

    response = await client.post(
        "/api/v1/auth/set-password",
        json={"new_password": NEW_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 404


async def test_changing_a_password_needs_the_csrf_header(client: AsyncClient, test_user: dict):
    await _login(client, test_user)

    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": test_user["password"], "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 403


async def test_me_answers_the_callers_identity(client: AsyncClient, test_user: dict):
    await _login(client, test_user)

    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["username"] == test_user["username"]
    assert response.json()["email"] == test_user["email"]
    assert response.json()["is_superuser"] is False


async def test_me_needs_a_session(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


async def test_the_account_routes_appear_once_in_the_api_docs():
    mounted = {
        route.path: list(route.tags)
        for route in app.routes
        if isinstance(route, APIRoute) and route.path in {"/api/v1/auth/me", "/api/v1/auth/change-password"}
    }

    assert mounted == {
        "/api/v1/auth/me": ["Authentication"],
        "/api/v1/auth/change-password": ["Authentication"],
    }
