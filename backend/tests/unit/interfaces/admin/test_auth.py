"""Tests for the SQLAdmin authentication backend."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.interfaces.admin.auth import AdminAuth


class FakeRequest:
    def __init__(self, form: dict[str, Any]) -> None:
        self._form = form
        self.session: dict[str, Any] = {}

    async def form(self) -> dict[str, Any]:
        return self._form


async def _login(configured: tuple[str, str], form: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    username, password = configured
    request = FakeRequest(form)
    settings = SimpleNamespace(ADMIN_USERNAME=username, ADMIN_PASSWORD=password)
    with patch("src.interfaces.admin.auth.get_settings", return_value=settings):
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
