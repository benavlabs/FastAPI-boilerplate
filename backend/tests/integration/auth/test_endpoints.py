"""Tests for the auth endpoints, now running on crudauth.

The OAuth routes drive module-level crudauth objects (``oauth_providers``,
``oauth_state_storage``) directly, so we patch those in the routes module. The
check-auth route depends on ``get_optional_principal``, so we override that
FastAPI dependency to simulate authenticated / anonymous callers.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crudauth import Principal, get_password_hash
from crudauth.oauth import OAuthState, OAuthUserInfo
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.dependencies import get_optional_principal
from src.interfaces.main import app
from src.modules.user.models import User

ROUTES = "src.infrastructure.auth.routes"


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
async def test_oauth_google_login(client: AsyncClient):
    """The Google login initiation endpoint returns the provider authorization URL."""
    mock_provider = MagicMock()
    mock_provider.get_authorization_url = MagicMock(
        return_value={
            "url": "https://accounts.google.com/o/oauth2/v2/auth?dummy=params",
            "state": "test-state-value",
            "code_verifier": "test-code-verifier",
        }
    )
    mock_storage = MagicMock()
    mock_storage.create = AsyncMock(return_value="test-state-value")

    with (
        patch(f"{ROUTES}.oauth_providers", {"google": mock_provider}),
        patch(f"{ROUTES}.oauth_state_storage", mock_storage),
    ):
        response = await client.get("/api/v1/auth/oauth/google")

    assert response.status_code == 200
    assert response.json()["url"] == "https://accounts.google.com/o/oauth2/v2/auth?dummy=params"
    mock_provider.get_authorization_url.assert_called_once()
    mock_storage.create.assert_called_once()


@pytest.mark.asyncio
async def test_oauth_callback_invalid_state(client: AsyncClient):
    """An unknown state parameter is rejected (302 redirect / 400 for json)."""
    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=None)

    with patch(f"{ROUTES}.oauth_state_storage", mock_storage):
        response = await client.get(
            "/api/v1/auth/oauth/callback/google",
            params={"code": "test-code", "state": "invalid-state"},
        )
        assert response.status_code == 302

        response = await client.get(
            "/api/v1/auth/oauth/callback/google",
            params={"code": "test-code", "state": "invalid-state", "response_format": "json"},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_oauth_callback_provider_mismatch(client: AsyncClient):
    """A state minted for a different provider is rejected (302 redirect / 400 for json)."""
    mismatched_state = OAuthState(
        state="test-state-value",
        provider="github",
        redirect_to="/",
        code_verifier="test-code-verifier",
    )
    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=mismatched_state)

    with patch(f"{ROUTES}.oauth_state_storage", mock_storage):
        response = await client.get(
            "/api/v1/auth/oauth/callback/google",
            params={"code": "test-code", "state": "test-state-value"},
        )
        assert response.status_code == 302

        response = await client.get(
            "/api/v1/auth/oauth/callback/google",
            params={"code": "test-code", "state": "test-state-value", "response_format": "json"},
        )
        assert response.status_code == 400


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
async def test_login_soft_deleted_user_rejected(client: AsyncClient, db_session: AsyncSession, test_tier: dict):
    """A soft-deleted user cannot log in — crudauth reads User.is_active (not is_deleted).

    This is the migration's core new invariant: the derived is_active property gates
    authentication, so is_deleted=True must fail login.
    """
    user = User(
        name="Deleted User",
        username="deleted_user",
        email="deleted@example.com",
        hashed_password=get_password_hash("Password123!"),
        tier_id=test_tier["id"],
    )
    user.is_deleted = True
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "deleted_user", "password": "Password123!"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_unauthenticated_returns_401(client: AsyncClient):
    """Logout with no session is rejected (the route depends on get_current_principal)."""
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
async def test_oauth_google_login_provider_failure_returns_500(client: AsyncClient):
    """If the provider blows up while building the auth URL, the endpoint returns 500."""
    mock_provider = MagicMock()
    mock_provider.get_authorization_url = MagicMock(side_effect=RuntimeError("boom"))

    with patch(f"{ROUTES}.oauth_providers", {"google": mock_provider}):
        response = await client.get("/api/v1/auth/oauth/google")

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_oauth_callback_success_creates_user(client: AsyncClient):
    """The happy-path callback links/creates the user and starts a session (json format).

    Exercises the real oauth_account_service.get_or_create_user → repo.create against
    the test DB (proving crudauth user creation works on the dataclass-mapped User),
    with only the provider's network calls mocked.
    """
    valid_state = OAuthState(
        state="good-state",
        provider="google",
        redirect_to="/",
        code_verifier="test-code-verifier",
    )
    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=valid_state)
    mock_storage.delete = AsyncMock(return_value=None)

    mock_provider = MagicMock()
    mock_provider.exchange_code = AsyncMock(return_value={"access_token": "tok"})
    mock_provider.get_user_info = AsyncMock(return_value={})
    mock_provider.process_user_info = AsyncMock(
        return_value=OAuthUserInfo(
            provider="google",
            provider_user_id="google-uid-123",
            email="oauth_new@example.com",
            email_verified=True,
            name="OAuth New User",
        )
    )

    with (
        patch(f"{ROUTES}.oauth_state_storage", mock_storage),
        patch(f"{ROUTES}.oauth_providers", {"google": mock_provider}),
    ):
        response = await client.get(
            "/api/v1/auth/oauth/callback/google",
            params={"code": "test-code", "state": "good-state", "response_format": "json"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["user"]["email"] == "oauth_new@example.com"
    assert body["user"]["is_new_user"] is True
    assert body["csrf_token"]
    mock_storage.delete.assert_awaited_once()


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
