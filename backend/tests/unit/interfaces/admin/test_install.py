"""What mounts the panel, and what it must not put on every API request.

A panel the project cannot sign anyone in to is not mounted at all: it would serve a login
form, and a stack banner, to anyone who asks. ``ADMIN_ENABLED`` has to be set for it, and
both credentials have to be there.
"""

import logging

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Mount

from src.infrastructure.config.settings import settings
from src.interfaces.admin.auth import RootPathSessionMiddleware, admin_base_url
from src.interfaces.admin.initialize import create_admin_interface
from src.interfaces.main import app
from tests.settings_defaults import declared_default
from tests.unit.interfaces.admin.helpers import configure_panel


def _middleware_classes(application) -> list[type]:
    return [middleware.cls for middleware in application.user_middleware]


def _mounted_panels(application: FastAPI) -> list[Mount]:
    return [route for route in application.routes if isinstance(route, Mount) and route.path == admin_base_url()]


def test_the_app_installs_no_session_middleware_of_its_own():
    assert SessionMiddleware not in _middleware_classes(app)


def test_the_admin_routes_carry_the_session_middleware_themselves(monkeypatch):
    mounted = [route.app for route in _mounted_panels(configure_panel(monkeypatch))]

    assert mounted, "the panel is not mounted"
    assert any(RootPathSessionMiddleware in _middleware_classes(panel) for panel in mounted)


def test_the_panel_is_off_until_it_is_asked_for():
    """Enabled by default, an unconfigured deployment served a panel it had no password for."""
    assert declared_default("ADMIN_ENABLED") == "False"


def test_a_panel_with_a_credential_missing_is_not_mounted(monkeypatch, caplog):
    """Mounted, it would answer the login form that an empty password can never pass."""
    monkeypatch.setattr(settings, "ADMIN_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
    application = FastAPI()

    with caplog.at_level(logging.WARNING):
        panel = create_admin_interface(application)

    assert panel is None
    assert _mounted_panels(application) == []
    assert "ADMIN_PASSWORD" in caplog.text
