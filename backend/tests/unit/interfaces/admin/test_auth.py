"""Tests for the SQLAdmin authentication backend."""

import pytest
from starlette.middleware import Middleware

from src.infrastructure.auth.setup import session_transport
from src.infrastructure.config.settings import EnvironmentOption, settings
from src.interfaces.admin.auth import (
    SESSION_MAX_AGE_SECONDS,
    AdminAuth,
    RootPathSessionMiddleware,
    admin_base_url,
)
from tests.unit.interfaces.admin.helpers import CLIENT, admin_login, clear_admin_lockout, configure_panel


def session_middleware(backend: AdminAuth) -> Middleware:
    """The panel's session middleware, whatever else the panel mounts in front of it."""
    return next(mounted for mounted in backend.middlewares if mounted.cls is RootPathSessionMiddleware)


@pytest.fixture
async def panel(monkeypatch):
    """The panel mounted on its own app, with a clean lockout for the test client."""
    await clear_admin_lockout(CLIENT)

    yield lambda **credentials: configure_panel(monkeypatch, **credentials)

    await clear_admin_lockout(CLIENT)


@pytest.mark.parametrize(
    ("configured", "form"),
    [
        (("", ""), {"username": "", "password": ""}),
        (("admin", ""), {"username": "admin", "password": ""}),
        (("", "s3cret"), {"username": "", "password": "s3cret"}),
    ],
)
async def test_login_is_disabled_until_both_credentials_are_configured(panel, monkeypatch, configured, form):
    """A panel with no credentials is not mounted, so this empties them after it is."""
    mounted = panel()
    username, password = configured
    monkeypatch.setattr(settings, "ADMIN_USERNAME", username)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", password)

    status, cookie = await admin_login(mounted, **form)

    assert status == 400
    assert "admin_session" not in cookie


async def test_login_with_configured_credentials_starts_admin_session(panel):
    status, cookie = await admin_login(panel())

    assert status == 302
    assert "admin_session" in cookie


@pytest.mark.parametrize(
    "form",
    [
        {"username": "admin", "password": "wrong"},
        {"username": "wrong", "password": "s3cret"},
        {"username": "admin", "password": ""},
    ],
)
async def test_login_rejects_wrong_credentials(panel, form):
    status, cookie = await admin_login(panel(), **form)

    assert status == 400
    assert "admin_session" not in cookie


async def test_login_rejects_non_ascii_input_without_raising(panel):
    status, _ = await admin_login(panel(), username="admín", password="s3cret")

    assert status == 400


async def test_login_accepts_non_ascii_configured_password(panel):
    status, cookie = await admin_login(panel(password="contraseña"), username="admin", password="contraseña")

    assert status == 302
    assert "admin_session" in cookie


def test_the_admin_session_cookie_is_scoped_and_short_lived(monkeypatch):
    """The cookie expires in hours, and outside local and development never travels over HTTP."""
    monkeypatch.setattr(settings, "ENVIRONMENT", EnvironmentOption.PRODUCTION)

    options = session_middleware(AdminAuth(secret_key="a-secret")).kwargs

    assert options["https_only"] is True
    assert options["max_age"] == SESSION_MAX_AGE_SECONDS
    assert options["same_site"] == "strict"
    assert options["session_cookie"] == "admin_session"
    assert options["session_cookie"] != session_transport.cookie_name
    assert options["base_url"] == admin_base_url()


def test_the_cookie_may_travel_over_http_in_development(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", EnvironmentOption.LOCAL)

    assert session_middleware(AdminAuth(secret_key="a-secret")).kwargs["https_only"] is False
