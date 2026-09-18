"""Authentication backend for SQLAdmin."""

import hmac

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from ...infrastructure.config.settings import get_settings


def _credential_matches(submitted: object, expected: str) -> bool:
    """Compare a submitted credential against the configured one in constant time."""
    if not isinstance(submitted, str):
        return False
    return hmac.compare_digest(submitted.encode(), expected.encode())


class AdminAuth(AuthenticationBackend):
    """Session-based authentication for the admin interface."""

    async def login(self, request: Request) -> bool:
        """Validate login credentials and create session."""
        form = await request.form()
        settings = get_settings()

        if not settings.ADMIN_USERNAME or not settings.ADMIN_PASSWORD:
            return False

        username_matches = _credential_matches(form.get("username"), settings.ADMIN_USERNAME)
        password_matches = _credential_matches(form.get("password"), settings.ADMIN_PASSWORD)

        if username_matches and password_matches:
            request.session.update({"admin_authenticated": True})
            return True

        return False

    async def logout(self, request: Request) -> bool:
        """Clear the admin session."""
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        """Check if the current request is authenticated."""
        return bool(request.session.get("admin_authenticated", False))
