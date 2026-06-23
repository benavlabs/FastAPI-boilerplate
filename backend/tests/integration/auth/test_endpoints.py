"""Tests for the auth endpoints, now running on crudauth.

The OAuth routes drive module-level crudauth objects (``oauth_providers``,
``oauth_state_storage``) directly, so we patch those in the routes module. The
check-auth route depends on ``get_optional_principal``, so we override that
FastAPI dependency to simulate authenticated / anonymous callers.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crudauth import Principal
from crudauth.oauth import OAuthState
from httpx import AsyncClient

from src.infrastructure.auth.dependencies import get_optional_principal
from src.interfaces.main import app

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
        app.dependency_overrides[get_optional_principal] = lambda: Principal(
            user_id=1, metadata={"session_id": "test-session"}
        )

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
