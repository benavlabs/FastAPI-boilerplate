"""SQLAdmin interface initialization."""

from fastapi import FastAPI
from sqladmin import Admin

from ...infrastructure.config.settings import get_settings
from ...infrastructure.database.session import get_engine
from ...wiring.admin import ADMIN_VIEWS
from .auth import AdminAuth


def create_admin_interface(app: FastAPI) -> Admin | None:
    """Create and configure the SQLAdmin interface.

    Args:
        app: The FastAPI application instance.

    Returns:
        Configured Admin instance or None if admin is disabled.
    """
    settings = get_settings()

    if not settings.ADMIN_ENABLED:
        return None

    authentication_backend = AdminAuth(secret_key=settings.SECRET_KEY)

    admin = Admin(
        app=app,
        engine=get_engine(),
        authentication_backend=authentication_backend,
        title="Admin",
    )

    for view in ADMIN_VIEWS:
        admin.add_view(view)

    return admin


def install(app: FastAPI) -> None:
    """Mount the admin panel.

    The panel brings its own session middleware, scoped to its routes, so an API
    request never decodes an admin cookie.
    """
    create_admin_interface(app)
