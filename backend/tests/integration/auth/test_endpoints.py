"""Tests for the auth endpoints, now running on crudauth.

The check-auth route depends on ``get_optional_principal``, so we override that
FastAPI dependency to simulate authenticated / anonymous callers.
"""

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import bcrypt
import pytest
from crudauth import Principal, get_password_hash
from crudauth.transports.session.schemas import SessionData
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth import routes
from src.infrastructure.auth.dependencies import get_optional_principal
from src.infrastructure.auth.setup import auth as crud_auth
from src.infrastructure.config.settings import settings
from src.interfaces.main import app
from src.modules.user.models import User

pytestmark = pytest.mark.usefixtures("fresh_login_lockout")


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: dict):
    """A valid username/password logs in: 200, a CSRF token, and a session cookie.

    Exercises the real crudauth path end-to-end (authenticate_password against the
    test DB, create_session on the in-memory backend, set_session_cookies).
    """
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )

    assert response.status_code == 200
    assert response.json()["csrf_token"]
    assert any(cookie == "session_id" for cookie in response.cookies)


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user: dict):
    """An incorrect password is rejected with 401."""
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": "wrong-password"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_then_logout(client: AsyncClient, test_user: dict):
    """Logging in then logging out (echoing the CSRF token) succeeds and clears the session."""
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )
    assert login.status_code == 200
    csrf_token = login.json()["csrf_token"]

    logout = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})

    assert logout.status_code == 200
    assert logout.json()["message"] == "Logged out successfully"


@pytest.mark.asyncio
async def test_check_auth_authenticated(client: AsyncClient):
    """check-auth returns the user info when a principal is resolved."""
    mock_user = {
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "oauth_provider": "google",
    }

    original_deps = app.dependency_overrides.copy()
    try:
        app.dependency_overrides[get_optional_principal] = lambda: Principal(user_id=1, metadata={"session_id": "test-session"})

        with patch("src.modules.user.crud.crud_users.get", return_value=mock_user):
            response = await client.get("/api/v1/auth/check-auth")

        assert response.status_code == 200
        body = response.json()
        assert body["authenticated"] is True
        assert body["user"]["id"] == 1
        assert body["user"]["username"] == "testuser"
        assert body["user"]["oauth_provider"] == "google"
        assert "session" in body
    finally:
        app.dependency_overrides = original_deps


@pytest.mark.asyncio
async def test_check_auth_not_authenticated(client: AsyncClient):
    """check-auth returns authenticated=false when the principal is None."""
    original_deps = app.dependency_overrides.copy()
    try:
        app.dependency_overrides[get_optional_principal] = lambda: None

        response = await client.get("/api/v1/auth/check-auth")

        assert response.status_code == 200
        assert response.json()["authenticated"] is False
        assert response.json()["message"] == "Not authenticated"
    finally:
        app.dependency_overrides = original_deps


@pytest.mark.asyncio
async def test_check_auth_no_session_cookie_returns_unauthenticated(client: AsyncClient):
    """A request with no session cookie gets 200 {authenticated: false}, not a 401.

    No dependency override here: the real crudauth ``current_user(optional=True)``
    resolution runs against a request that carries no session cookie, proving the
    endpoint answers anonymous callers rather than raising 401.
    """
    response = await client.get("/api/v1/auth/check-auth")

    assert response.status_code == 200
    assert response.json()["authenticated"] is False


@pytest.mark.asyncio
async def test_login_soft_deleted_user_rejected(client: AsyncClient, db_session: AsyncSession):
    """A soft-deleted user cannot log in — crudauth reads User.is_active (not is_deleted).

    This is the migration's core new invariant: the derived is_active property gates
    authentication, so is_deleted=True must fail login.
    """
    user = User(
        name="Deleted User",
        username="deleted_user",
        email="deleted@example.com",
        hashed_password=get_password_hash("Password123!"),
    )
    user.is_deleted = True
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "deleted_user", "password": "Password123!"},
    )

    assert response.status_code == 401


class TestTheAbsoluteSessionCap:
    """``SESSION_ABSOLUTE_TIMEOUT_HOURS`` ends a session however active it stays."""

    @pytest.fixture
    def capped_at_twelve_hours(self, monkeypatch):
        monkeypatch.setattr(crud_auth.sessions, "absolute_timeout", timedelta(hours=12))

    async def _age(self, session_id: str, hours: int) -> None:
        """Move the session's sign-in time ``hours`` into the past."""
        signed_in_at = datetime.now(UTC) - timedelta(hours=hours)

        def backdate(session: SessionData) -> None:
            session.created_at = signed_in_at

        assert await crud_auth.sessions.modify_session(session_id, backdate) is not None

    async def test_a_session_past_the_cap_is_refused_and_gone(
        self, client: AsyncClient, test_user: dict, capped_at_twelve_hours
    ):
        session_id, _ = await _login(client, test_user)
        await self._age(session_id, hours=13)

        authenticated = await _is_authenticated(client, session_id)

        assert authenticated is False
        assert await crud_auth.sessions.validate_session(session_id) is None

    async def test_a_session_inside_the_cap_is_untouched(self, client: AsyncClient, test_user: dict, capped_at_twelve_hours):
        session_id, _ = await _login(client, test_user)
        await self._age(session_id, hours=11)

        assert await _is_authenticated(client, session_id) is True


@pytest.mark.asyncio
async def test_logout_runs_the_after_logout_hook(client: AsyncClient, test_user: dict, monkeypatch):
    """An audit log hangs off this hook, and it names the session that ended."""
    logged: list[tuple[dict, str | None]] = []

    async def record(user: dict, *, request, context) -> None:
        logged.append((user, context.session_handle))

    monkeypatch.setattr(crud_auth.hooks, "on_after_logout", record)
    session_id, csrf_token = await _login(client, test_user)

    response = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    assert [(user["username"], handle) for user, handle in logged] == [
        (test_user["username"], crud_auth.sessions.session_handle(session_id))
    ]


@pytest.mark.asyncio
async def test_logout_unauthenticated_returns_401(client: AsyncClient):
    """Logout with no session is rejected (the route depends on get_session_principal)."""
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_without_csrf_token_rejected(client: AsyncClient, test_user: dict):
    """A logged-in session still can't mutate without the CSRF header (403)."""
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )
    assert login.status_code == 200

    # POST without the X-CSRF-Token header → crudauth CSRF guard rejects with 403.
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 403


async def _clear_sessions(user: dict) -> None:
    """Drop sessions left for this user id by earlier tests.

    crudauth's in-memory session store lives for the whole test run, while each test's
    fresh database hands ``test_user`` the same id, so leftovers would skew the counts.
    """
    await crud_auth.sessions.revoke_all(user["id"])


async def _login(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Log in and return the new session's ``(session_id, csrf_token)``."""
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": user["username"], "password": user["password"]},
    )
    assert response.status_code == 200
    return response.cookies["session_id"], response.json()["csrf_token"]


@asynccontextmanager
async def _another_browser(user: dict) -> AsyncIterator[tuple[AsyncClient, str]]:
    """A second signed-in client and its session id, closed however the test ends.

    A login revokes the session the browser it came from presented, so two sessions of
    one account need two cookie jars.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        session_id, _ = await _login(other, user)

        yield other, session_id


async def _is_authenticated(client: AsyncClient, session_id: str | None = None) -> bool:
    """check-auth as the client's current session, or as ``session_id`` when given."""
    if session_id is not None:
        client.cookies.clear()
        client.cookies.set("session_id", session_id)
    response = await client.get("/api/v1/auth/check-auth")
    assert response.status_code == 200
    authenticated: bool = response.json()["authenticated"]

    return authenticated


@pytest.mark.asyncio
async def test_logout_all_terminates_every_session(client: AsyncClient, test_user: dict):
    """logout-all revokes every session of the user (not just the caller's) and clears cookies."""
    await _clear_sessions(test_user)
    async with _another_browser(test_user) as (other, other_session_id):
        _, csrf_token = await _login(client, test_user)

        response = await client.post("/api/v1/auth/logout-all", headers={"X-CSRF-Token": csrf_token})

        assert response.status_code == 200
        assert response.json()["terminated_count"] == 2
        assert any(c.startswith("session_id=") for c in response.headers.get_list("set-cookie"))
        assert await _is_authenticated(other, other_session_id) is False


@pytest.mark.asyncio
async def test_logout_all_keep_current_spares_calling_session(client: AsyncClient, test_user: dict):
    """keep_current=true revokes the other sessions but keeps the caller's session and cookies."""
    await _clear_sessions(test_user)
    async with _another_browser(test_user) as (other, other_session_id):
        own_session_id, csrf_token = await _login(client, test_user)

        response = await client.post(
            "/api/v1/auth/logout-all",
            params={"keep_current": "true"},
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 200
        assert response.json()["terminated_count"] == 1
        assert not any(c.startswith("session_id=") for c in response.headers.get_list("set-cookie"))
        assert await _is_authenticated(client, own_session_id) is True
        assert await _is_authenticated(other, other_session_id) is False


@pytest.mark.asyncio
async def test_signing_in_again_ends_the_session_the_browser_presented(client: AsyncClient, test_user: dict):
    """A copied cookie stops working as soon as the browser it came from signs in again."""
    await _clear_sessions(test_user)
    first_session_id, _ = await _login(client, test_user)

    second_session_id, _ = await _login(client, test_user)

    assert second_session_id != first_session_id
    assert await _is_authenticated(client, second_session_id) is True
    assert await _is_authenticated(client, first_session_id) is False


@pytest.mark.asyncio
async def test_logout_all_unauthenticated_returns_401(client: AsyncClient):
    """logout-all with no session is rejected."""
    response = await client.post("/api/v1/auth/logout-all")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_all_without_csrf_token_rejected(client: AsyncClient, test_user: dict):
    """A logged-in session can't log out everywhere without the CSRF header (403)."""
    await _login(client, test_user)

    response = await client.post("/api/v1/auth/logout-all")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_refresh_csrf_token_success(client: AsyncClient, test_user: dict):
    """With a valid session cookie, /refresh-csrf mints a fresh token (no CSRF header needed)."""
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )
    assert login.status_code == 200

    response = await client.post("/api/v1/auth/refresh-csrf")

    assert response.status_code == 200
    assert response.json()["csrf_token"]


@pytest.mark.asyncio
async def test_refresh_csrf_token_no_session_returns_401(client: AsyncClient):
    """/refresh-csrf with no session cookie is unauthorized."""
    response = await client.post("/api/v1/auth/refresh-csrf")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_check_auth_user_not_found(client: AsyncClient):
    """A resolved principal whose user row is missing reports authenticated=false."""
    original_deps = app.dependency_overrides.copy()
    try:
        app.dependency_overrides[get_optional_principal] = lambda: Principal(user_id=999999, metadata={"session_id": "x"})

        with patch("src.modules.user.crud.crud_users.get", return_value=None):
            response = await client.get("/api/v1/auth/check-auth")

        assert response.status_code == 200
        assert response.json()["authenticated"] is False
        assert response.json()["message"] == "User not found"
    finally:
        app.dependency_overrides = original_deps


def _credentials(user: dict) -> dict:
    return {"username": user["username"], "password": user["password"]}


@pytest.mark.asyncio
async def test_login_returns_the_user_and_the_csrf_token(client: AsyncClient, test_user: dict):
    response = await client.post("/api/v1/auth/login", data=_credentials(test_user))

    body = response.json()
    assert body["id"] == test_user["id"]
    assert body["username"] == test_user["username"]
    assert body["csrf_token"]


@pytest.mark.asyncio
async def test_a_cross_site_login_is_refused(client: AsyncClient, test_user: dict):
    """Another site can't sign the visitor into an account it controls (login CSRF)."""
    response = await client.post("/api/v1/auth/login", data=_credentials(test_user), headers={"Sec-Fetch-Site": "cross-site"})

    assert response.status_code == 403
    assert "session_id" not in response.cookies


@pytest.mark.asyncio
@pytest.mark.parametrize("fetch_site", ["same-origin", "same-site", "none"])
async def test_a_first_party_login_is_accepted(client: AsyncClient, test_user: dict, fetch_site: str):
    response = await client.post("/api/v1/auth/login", data=_credentials(test_user), headers={"Sec-Fetch-Site": fetch_site})

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_remember_me_makes_the_session_cookie_persistent(client: AsyncClient, test_user: dict):
    remembered = await client.post("/api/v1/auth/login", data={**_credentials(test_user), "remember_me": "true"})
    client.cookies.clear()
    forgotten = await client.post("/api/v1/auth/login", data=_credentials(test_user))

    def session_cookie(response: Response) -> str:
        cookie: str = next(c for c in response.headers.get_list("set-cookie") if c.startswith("session_id="))

        return cookie

    assert "max-age" in session_cookie(remembered).lower()
    assert "max-age" not in session_cookie(forgotten).lower()


@pytest.mark.asyncio
async def test_signup_hashes_the_password_off_the_event_loop(client: AsyncClient, db_session: AsyncSession):
    """bcrypt is deliberately slow; on the loop thread it would stall every other request."""
    real_hashpw = bcrypt.hashpw
    threads: list[str] = []

    def recording_hashpw(password, salt):
        threads.append(threading.current_thread().name)
        return real_hashpw(password, salt)

    with patch.object(bcrypt, "hashpw", recording_hashpw):
        response = await client.post(
            "/api/v1/users/",
            json={"name": "Off Loop", "username": "offloop", "email": "off.loop@example.com", "password": "Str1ngst!"},
        )

    assert response.status_code == 201
    assert threads
    assert threading.main_thread().name not in threads


@pytest.mark.asyncio
async def test_login_finishes_through_the_session_transport(client: AsyncClient, test_user: dict):
    """The route must create the session through SessionTransport.complete_login (cookies + hooks)."""
    captured: dict = {}
    original = routes.session_transport.complete_login

    async def spy(request, response, user, options):
        captured["options"] = options
        return await original(request, response, user, options)

    with patch.object(routes.session_transport, "complete_login", spy):
        response = await client.post(
            "/api/v1/auth/login",
            data={**_credentials(test_user), "remember_me": "true"},
        )

    assert response.status_code == 200
    assert captured["options"]["remember_me"] is True
    assert captured["options"]["metadata"]["login_type"] == "password"


@pytest.mark.asyncio
async def test_a_login_is_refused_while_the_lockout_backend_is_down(client: AsyncClient, test_user: dict, monkeypatch):
    """The lockout fails closed, so an outage must not open the door to brute force.

    Documented in docs/user-guide/authentication/sessions.md.
    """

    class UnreachableBackend:
        async def get_ttl(self, key: str) -> int:
            raise ConnectionError("limiter redis is down")

        async def increment(self, key: str, amount: int, expire: int) -> int:
            raise ConnectionError("limiter redis is down")

    monkeypatch.setattr(crud_auth.runtime.lockout, "backend", UnreachableBackend())

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_a_sixth_failure_inside_the_window_locks_the_login(client: AsyncClient, test_user: dict):
    """Five failures, then the right password answers 429 with the configured base duration."""
    for _ in range(5):
        refused = await client.post(
            "/api/v1/auth/login",
            data={"username": test_user["username"], "password": "wrong-password"},
        )
        assert refused.status_code == 401

    locked = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )

    assert locked.status_code == 429
    assert settings.LOGIN_LOCKOUT_BASE_SECONDS - 5 <= int(locked.headers["retry-after"]) <= settings.LOGIN_LOCKOUT_BASE_SECONDS
    assert "set-cookie" not in locked.headers


@pytest.mark.asyncio
async def test_a_successful_login_clears_the_failures(client: AsyncClient, test_user: dict):
    """Four failures, a login, four more and a login: neither run reaches the cap."""
    credentials = {"username": test_user["username"], "password": test_user["password"]}

    for _ in range(settings.LOGIN_MAX_ATTEMPTS - 1):
        assert (await client.post("/api/v1/auth/login", data={**credentials, "password": "wrong"})).status_code == 401
    assert (await client.post("/api/v1/auth/login", data=credentials)).status_code == 200

    for _ in range(settings.LOGIN_MAX_ATTEMPTS - 1):
        assert (await client.post("/api/v1/auth/login", data={**credentials, "password": "wrong"})).status_code == 401

    assert (await client.post("/api/v1/auth/login", data=credentials)).status_code == 200
