"""Tests for the SQLAdmin authentication backend."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.infrastructure.config.settings import EnvironmentOption, settings
from src.interfaces.admin.auth import ADMIN_COOKIE_PATH, SESSION_MAX_AGE_SECONDS, AdminAuth


class FakeRequest:
    def __init__(self, form: dict[str, Any]) -> None:
        self._form = form
        self.session: dict[str, Any] = {}

    async def form(self) -> dict[str, Any]:
        return self._form


async def _login(configured: tuple[str, str], form: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    username, password = configured
    request = FakeRequest(form)
    configured_settings = SimpleNamespace(
        ADMIN_USERNAME=username,
        ADMIN_PASSWORD=password,
        ENVIRONMENT=EnvironmentOption.LOCAL,
    )
    with patch("src.interfaces.admin.auth.get_settings", return_value=configured_settings):
        authenticated = await AdminAuth(secret_key="test").login(request)
    return authenticated, request.session


@pytest.mark.parametrize(
    ("configured", "form"),
    [
        (("", ""), {"username": "", "password": ""}),
        (("admin", ""), {"username": "admin", "password": ""}),
        (("", "s3cret"), {"username": "", "password": "s3cret"}),
    ],
)
async def test_login_is_disabled_until_both_credentials_are_configured(configured, form):
    authenticated, session = await _login(configured, form)

    assert authenticated is False
    assert session == {}


async def test_login_with_configured_credentials_starts_admin_session():
    authenticated, session = await _login(("admin", "s3cret"), {"username": "admin", "password": "s3cret"})

    assert authenticated is True
    assert session == {"admin_authenticated": True}


@pytest.mark.parametrize(
    "form",
    [
        {"username": "admin", "password": "wrong"},
        {"username": "wrong", "password": "s3cret"},
        {"username": "admin"},
        {},
    ],
)
async def test_login_rejects_wrong_or_missing_credentials(form):
    authenticated, session = await _login(("admin", "s3cret"), form)

    assert authenticated is False
    assert session == {}


async def test_login_rejects_non_ascii_input_without_raising():
    authenticated, session = await _login(("admin", "s3cret"), {"username": "admín", "password": "s3cret"})

    assert authenticated is False
    assert session == {}


async def test_login_accepts_non_ascii_configured_password():
    authenticated, session = await _login(("admin", "contraseña"), {"username": "admin", "password": "contraseña"})

    assert authenticated is True
    assert session == {"admin_authenticated": True}


def test_the_admin_session_cookie_is_scoped_and_short_lived(monkeypatch):
    """Nothing can revoke this cookie, so it expires in hours and never travels over HTTP."""
    monkeypatch.setattr(settings, "ENVIRONMENT", EnvironmentOption.PRODUCTION)

    middleware = AdminAuth(secret_key="a-secret").middlewares

    assert len(middleware) == 1
    options = middleware[0].kwargs
    assert options["https_only"] is True
    assert options["max_age"] == SESSION_MAX_AGE_SECONDS
    assert options["session_cookie"] == "admin_session"
    assert options["path"] == ADMIN_COOKIE_PATH


def test_the_cookie_may_travel_over_http_in_development(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", EnvironmentOption.LOCAL)

    assert AdminAuth(secret_key="a-secret").middlewares[0].kwargs["https_only"] is False
