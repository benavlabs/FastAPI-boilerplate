"""The panel's mount path, and the cookie that has to follow it."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.infrastructure.config.settings import EnvironmentOption, settings
from src.interfaces.admin.initialize import create_admin_interface
from src.interfaces.main import app as application

pytestmark = pytest.mark.asyncio

CREDENTIALS = {"username": "admin", "password": "s3cret"}


@pytest.fixture
def configured(monkeypatch):
    """An admin panel with credentials, outside production."""
    monkeypatch.setattr(settings, "ADMIN_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_USERNAME", CREDENTIALS["username"])
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", CREDENTIALS["password"])
    monkeypatch.setattr(settings, "ENVIRONMENT", EnvironmentOption.LOCAL)

    return monkeypatch


async def _login_then_open(app: FastAPI, base_url: str, root_path: str = "") -> tuple[int, str, int]:
    """Log in and load the panel's index, reporting the statuses and the cookie the login set."""
    transport = ASGITransport(app=app, root_path=root_path)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(f"{root_path}{base_url}/login", data=CREDENTIALS, follow_redirects=False)
        cookie = login.headers.get("set-cookie", "")
        index = await client.get(f"{root_path}{base_url}/", follow_redirects=False)

    return login.status_code, cookie, index.status_code


def _panel() -> FastAPI:
    """An app with the panel mounted, as the app factory mounts it."""
    app = FastAPI()
    create_admin_interface(app)

    return app


async def test_the_default_mount_keeps_a_session(configured):
    login_status, cookie, index_status = await _login_then_open(_panel(), "/admin")

    assert login_status == 302
    assert "path=/admin" in cookie
    assert index_status == 200


async def test_a_custom_mount_keeps_a_session(configured):
    configured.setattr(settings, "ADMIN_BASE_URL", "/management")

    login_status, cookie, index_status = await _login_then_open(_panel(), "/management")

    assert login_status == 302
    assert "path=/management" in cookie
    assert index_status == 200


async def test_a_prefix_the_server_sets_is_part_of_the_cookie_path(configured):
    """``--root-path /svc`` reaches the app per request, and the cookie has to follow it."""
    login_status, cookie, index_status = await _login_then_open(application, "/admin", root_path="/svc")

    assert login_status == 302
    assert "path=/svc/admin" in cookie
    assert index_status == 200


async def test_the_same_app_without_a_prefix_scopes_the_cookie_to_the_mount(configured):
    login_status, cookie, index_status = await _login_then_open(application, "/admin")

    assert login_status == 302
    assert "path=/admin;" in cookie
    assert index_status == 200


async def test_a_base_url_naming_no_path_is_refused(configured):
    configured.setattr(settings, "ADMIN_BASE_URL", "/")

    with pytest.raises(ValueError, match="ADMIN_BASE_URL"):
        create_admin_interface(FastAPI())


@pytest.mark.parametrize("configured_value", ["admin", "/admin/", "admin/"])
async def test_a_base_url_is_read_whichever_way_it_is_written(configured, configured_value: str):
    configured.setattr(settings, "ADMIN_BASE_URL", configured_value)

    login_status, cookie, index_status = await _login_then_open(_panel(), "/admin")

    assert login_status == 302
    assert "path=/admin;" in cookie
    assert index_status == 200
