"""Mounting the panel must not put its session middleware on every API request."""

from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Mount

from src.interfaces.admin.auth import RootPathSessionMiddleware, admin_base_url
from src.interfaces.main import app


def _middleware_classes(application) -> list[type]:
    return [middleware.cls for middleware in application.user_middleware]


def test_the_app_installs_no_session_middleware_of_its_own():
    assert SessionMiddleware not in _middleware_classes(app)


def test_the_admin_routes_carry_the_session_middleware_themselves():
    admin_apps = [route.app for route in app.routes if isinstance(route, Mount) and route.path == admin_base_url()]

    assert admin_apps, "the panel is not mounted"
    assert any(RootPathSessionMiddleware in _middleware_classes(mounted) for mounted in admin_apps)
