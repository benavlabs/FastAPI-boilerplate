"""Google sign-in through crudauth's OAuth router, as the app mounts it."""

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.setup import auth
from src.infrastructure.config.settings import settings
from src.interfaces.main import app
from src.modules.user.constants import NAME_MAX_LENGTH, USERNAME_MAX_LENGTH
from src.modules.user.models import User

pytestmark = pytest.mark.asyncio

BASE = settings.OAUTH_REDIRECT_BASE_URL.rstrip("/")
CALLBACK = f"{BASE}/api/v1/auth/oauth/callback/google"


def _stub_google(monkeypatch, profile: dict) -> None:
    """Answer the token exchange and userinfo calls without reaching Google."""
    provider = auth.oauth_providers["google"]

    async def exchange_code(code, code_verifier=None, headers=None):
        return {"access_token": "google-access-token", "token_type": "Bearer"}

    async def get_user_info(access_token):
        return profile

    monkeypatch.setattr(provider, "exchange_code", exchange_code)
    monkeypatch.setattr(provider, "get_user_info", get_user_info)


async def _start(client: AsyncClient, **params) -> str:
    """Begin a sign-in and return the state Google would echo back."""
    response = await client.get("/api/v1/auth/oauth/google", params=params, follow_redirects=False)
    assert response.status_code == 307
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


async def test_google_is_told_to_return_to_the_route_that_serves_the_callback():
    """The URI Google redirects to must be one the app actually routes."""
    assert auth.oauth_providers["google"].redirect_uri == CALLBACK
    assert "/api/v1/auth/oauth/callback/{provider}" in {route.path for route in app.routes if isinstance(route, APIRoute)}


async def test_authorize_sends_the_browser_to_google_with_pkce(client: AsyncClient):
    response = await client.get("/api/v1/auth/oauth/google", follow_redirects=False)

    assert response.status_code == 307
    location = urlparse(response.headers["location"])
    params = parse_qs(location.query)
    assert location.netloc == "accounts.google.com"
    assert params["redirect_uri"] == [CALLBACK]
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"]


async def test_a_successful_callback_signs_the_user_in_and_returns_them(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    _stub_google(
        monkeypatch,
        {
            "sub": "google-123",
            "email": "grace.hopper@example.com",
            "email_verified": True,
            "name": "Grace Hopper",
            "given_name": "Grace",
            "picture": "https://example.com/grace.png",
        },
    )
    state = await _start(client, redirect_to="/dashboard")

    response = await client.get(
        "/api/v1/auth/oauth/callback/google", params={"code": "the-code", "state": state}, follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"] == "/dashboard"
    assert "session_id" in response.cookies
    user = (await db_session.execute(select(User).where(User.email == "grace.hopper@example.com"))).scalar_one()
    assert user.name == "Grace Hopper"
    assert user.google_id == "google-123"
    check = await client.get("/api/v1/auth/check-auth")
    assert check.json()["authenticated"] is True


async def test_long_provider_names_fit_the_user_columns(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    """Generated usernames and display names are bounded to the model's column widths."""
    long_name = "Wolfeschlegelsteinhausenbergerdorff Hubert Blaine Senior"
    _stub_google(
        monkeypatch,
        {
            "sub": "google-456",
            "email": "hubert@example.com",
            "email_verified": True,
            "name": long_name,
            "given_name": "Hubert",
        },
    )
    state = await _start(client)

    response = await client.get(
        "/api/v1/auth/oauth/callback/google", params={"code": "the-code", "state": state}, follow_redirects=False
    )

    assert response.status_code == 307
    user = (await db_session.execute(select(User).where(User.google_id == "google-456"))).scalar_one()
    assert 0 < len(user.name) <= NAME_MAX_LENGTH
    assert 0 < len(user.username) <= USERNAME_MAX_LENGTH


async def test_an_email_longer_than_the_column_is_refused_cleanly(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    """An address that can't be stored ends the sign-in with an error, not a 500."""
    _stub_google(
        monkeypatch,
        {
            "sub": "google-999",
            "email": f"{'a' * 60}@example.com",
            "email_verified": True,
            "name": "Long Address",
        },
    )
    state = await _start(client)

    response = await client.get(
        "/api/v1/auth/oauth/callback/google", params={"code": "the-code", "state": state}, follow_redirects=False
    )

    assert response.status_code == 307
    assert parse_qs(urlparse(response.headers["location"]).query)["error"] == ["email_too_long"]
    assert (await db_session.execute(select(User).where(User.google_id == "google-999"))).scalar_one_or_none() is None


async def test_an_offsite_redirect_target_falls_back_to_the_app(client: AsyncClient, monkeypatch):
    _stub_google(
        monkeypatch,
        {"sub": "google-789", "email": "offsite@example.com", "email_verified": True, "name": "Off Site"},
    )
    state = await _start(client, redirect_to="//evil.example.com/steal")

    response = await client.get(
        "/api/v1/auth/oauth/callback/google", params={"code": "the-code", "state": state}, follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"] == BASE


async def test_an_absolute_same_origin_redirect_is_refused(client: AsyncClient, monkeypatch):
    """Only relative paths are safe to hand back, even when the host is the app's own."""
    _stub_google(
        monkeypatch,
        {"sub": "google-321", "email": "absolute@example.com", "email_verified": True, "name": "Absolute Target"},
    )
    state = await _start(client, redirect_to=f"{BASE}/dashboard")

    response = await client.get(
        "/api/v1/auth/oauth/callback/google", params={"code": "the-code", "state": state}, follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"] == BASE


async def test_a_state_this_browser_never_started_is_refused(client: AsyncClient):
    """A state without its browser-bound cookie may be a login-CSRF attempt, so no session."""
    response = await client.get(
        "/api/v1/auth/oauth/callback/google",
        params={"code": "the-code", "state": "never-issued"},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == f"{BASE}?error=invalid_state"
    assert "session_id" not in response.cookies


async def test_a_provider_error_sends_the_browser_back_with_an_error(client: AsyncClient):
    """The user declined at Google: back to the app, carrying the error code."""
    response = await client.get("/api/v1/auth/oauth/callback/google", params={"error": "access_denied"}, follow_redirects=False)

    assert response.status_code == 307
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}" == BASE
    assert parse_qs(location.query)["error"]


async def test_the_auth_paths_keep_their_existing_contract():
    """The migration to crudauth must not move the URLs clients already call."""
    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    for path in (
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/logout-all",
        "/api/v1/auth/refresh-csrf",
        "/api/v1/auth/check-auth",
        "/api/v1/auth/oauth/{provider}",
        "/api/v1/auth/oauth/callback/{provider}",
    ):
        assert path in paths


@pytest.mark.usefixtures("fresh_login_lockout")
async def test_a_provider_login_claims_an_account_that_was_signed_up_for(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """Signing up with someone's address must not survive that address proving itself.

    crudauth claims an unverified account when a verified provider login matches its
    email: the password stops working, so whoever registered first can't keep access.
    """
    signup = await client.post(
        "/api/v1/users/",
        json={
            "name": "Ada Lovelace",
            "username": "adalovelace",
            "email": "ada.lovelace@example.com",
            "password": "Registered1!",
        },
    )
    assert signup.status_code == 201

    _stub_google(
        monkeypatch,
        {
            "sub": "google-ada",
            "email": "ada.lovelace@example.com",
            "email_verified": True,
            "name": "Ada Lovelace",
        },
    )
    state = await _start(client)
    callback = await client.get(
        "/api/v1/auth/oauth/callback/google",
        params={"code": "the-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 307
    client.cookies.clear()

    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "adalovelace", "password": "Registered1!"},
    )

    assert login.status_code == 401
    claimed = (await db_session.execute(select(User).where(User.email == "ada.lovelace@example.com"))).scalar_one()
    await db_session.refresh(claimed)
    assert claimed.google_id == "google-ada"
    assert claimed.email_verified is True


@pytest.mark.usefixtures("fresh_login_lockout")
async def test_a_provider_login_claims_an_account_whose_address_was_changed(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch
):
    """Moving a verified account onto someone else's address must not carry the trust over.

    The owner cannot move it at all through their profile; an administrator can, and the
    move clears the verification, so a provider login for the new address claims the
    account rather than inheriting the old address's trust.
    """
    await db_session.execute(update(User).where(User.id == test_user["id"]).values(email_verified=True))
    await db_session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )
    assert login.status_code == 200

    with_a_session_alone = await client.patch(
        f"/api/v1/users/{test_user['username']}",
        json={"email": "victim@example.com"},
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
    )
    assert with_a_session_alone.status_code == 422

    await db_session.execute(
        update(User).where(User.id == test_user["id"]).values(email="victim@example.com", email_verified=False)
    )
    await db_session.commit()
    assert (await client.get("/api/v1/users/me")).status_code == 200
    old_session = dict(client.cookies)
    client.cookies.clear()

    _stub_google(
        monkeypatch,
        {"sub": "google-victim", "email": "victim@example.com", "email_verified": True, "name": "Victim"},
    )
    state = await _start(client)
    callback = await client.get(
        "/api/v1/auth/oauth/callback/google",
        params={"code": "the-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 307
    client.cookies.clear()

    for name, value in old_session.items():
        client.cookies.set(name, value)
    with_the_old_session = await client.get("/api/v1/users/me")
    client.cookies.clear()

    refused = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )

    assert with_the_old_session.status_code == 401
    assert refused.status_code == 401
    claimed = (await db_session.execute(select(User).where(User.id == test_user["id"]))).scalar_one()
    await db_session.refresh(claimed)
    assert claimed.google_id == "google-victim"


class TestASoftDeletedAccount:
    """``User.is_active`` is ``not is_deleted``, and crudauth refuses an inactive account."""

    @staticmethod
    async def _sign_in_as(client: AsyncClient, monkeypatch, email: str) -> str:
        _stub_google(
            monkeypatch,
            {"sub": "google-deleted", "email": email, "email_verified": True, "name": "Deleted Person"},
        )
        state = await _start(client)
        callback = await client.get(
            "/api/v1/auth/oauth/callback/google",
            params={"code": "the-code", "state": state},
            follow_redirects=False,
        )

        assert callback.status_code == 307
        assert "session_id" not in callback.cookies

        return callback.headers["location"]

    async def test_a_provider_sign_in_is_refused_and_claims_nothing(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch
    ):
        """Linking the provider id onto a deleted row would hand the account to whoever signs in."""
        await db_session.execute(update(User).where(User.id == test_user["id"]).values(is_deleted=True))
        await db_session.commit()

        location = await self._sign_in_as(client, monkeypatch, test_user["email"])

        assert location == f"{BASE}?error=account_inactive"
        refused = await db_session.get_one(User, test_user["id"])
        await db_session.refresh(refused)
        assert refused.google_id is None
        assert refused.oauth_provider is None

    async def test_the_refused_sign_in_leaves_the_row_as_it_was(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch
    ):
        """An unverified address stays unverified, and the password still signs in once restored."""
        await db_session.execute(update(User).where(User.id == test_user["id"]).values(is_deleted=True))
        await db_session.commit()

        await self._sign_in_as(client, monkeypatch, test_user["email"])

        untouched = await db_session.get_one(User, test_user["id"])
        await db_session.refresh(untouched)
        assert untouched.email_verified is False
        assert untouched.email == test_user["email"]

        await db_session.execute(update(User).where(User.id == test_user["id"]).values(is_deleted=False))
        await db_session.commit()
        signed_in = await client.post(
            "/api/v1/auth/login",
            data={"username": test_user["username"], "password": test_user["password"]},
        )

        assert signed_in.status_code == 200
