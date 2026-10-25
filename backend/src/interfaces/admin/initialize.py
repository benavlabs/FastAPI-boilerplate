"""SQLAdmin interface initialization."""

from fastapi import FastAPI
from sqladmin import Admin

from ...infrastructure.config.settings import get_settings
from ...infrastructure.database.session import get_engine
from ...infrastructure.logging import get_logger
from ...wiring.admin import ADMIN_VIEWS
from .auth import AdminAuth, admin_base_url
from .logout import sign_out_on_a_post_only

logger = get_logger()


def create_admin_interface(app: FastAPI) -> Admin | None:
    """Create and configure the SQLAdmin interface.

    Args:
        app: The FastAPI application instance.

    Returns:
        Configured Admin instance, or ``None`` where the panel has no credentials to
        sign anyone in with: ``ADMIN_ENABLED`` unset or false, or either of
        ``ADMIN_USERNAME`` and ``ADMIN_PASSWORD`` empty.
    """
    settings = get_settings()

    if not settings.ADMIN_ENABLED:
        return None

    if not settings.ADMIN_USERNAME or not settings.ADMIN_PASSWORD:
        logger.warning(
            "ADMIN_ENABLED is set, and ADMIN_USERNAME or ADMIN_PASSWORD is empty: the panel is not mounted. "
            "Set both to serve it."
        )
        return None

    base_url = admin_base_url()
    authentication_backend = AdminAuth(secret_key=settings.SECRET_KEY, base_url=base_url)

    admin = Admin(
        app=app,
        engine=get_engine(),
        authentication_backend=authentication_backend,
        base_url=base_url,
        title="Admin",
    )

    for view in ADMIN_VIEWS:
        admin.add_view(view)

    sign_out_on_a_post_only(admin)

    return admin


def install(app: FastAPI) -> None:
    """Mount the admin panel, with its own session middleware scoped to its routes."""
    create_admin_interface(app)
