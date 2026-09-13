"""SQLAdmin interface initialization."""

from sqladmin import Admin

from ...infrastructure.config.settings import get_settings
from ...infrastructure.database.session import get_engine
from .auth import AdminAuth
from .views import register_admin_views


def create_admin_interface(app) -> Admin | None:
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

    register_admin_views(admin)

    return admin
