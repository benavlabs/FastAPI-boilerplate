"""Authentication backend for SQLAdmin."""

import hmac
from typing import Literal

from sqladmin.authentication import AuthenticationBackend
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from ...infrastructure.config.settings import EnvironmentOption, get_settings

SESSION_MAX_AGE_SECONDS = 60 * 60 * 8


def admin_base_url() -> str:
    """Where the panel is mounted: ``ADMIN_BASE_URL`` with one leading slash and no trailing one.

    Raises:
        ValueError: ``ADMIN_BASE_URL`` names no path to mount the panel under.
    """
    configured = get_settings().ADMIN_BASE_URL.strip().strip("/")
    if not configured:
        raise ValueError("ADMIN_BASE_URL must name a path to mount the panel under, such as /admin.")

    return f"/{configured}"


def admin_cookie_path(root_path: str, base_url: str) -> str:
    """The path the admin session cookie is scoped to: the mount a request arrived through.

    Inside the mounted panel, ``scope["root_path"]`` already carries the mount and any
    prefix the server was started with. ``base_url`` answers for a panel served on its
    own, with no mount in front of it.
    """
    return root_path.rstrip("/") or base_url


class RootPathSessionMiddleware:
    """Starlette's session middleware, with the cookie scoped to the path of each request's mount.

    Reads ``scope["root_path"]`` per request - where a prefix set with ``--root-path``
    arrives - and delegates to a session middleware scoped to that path, keeping one
    per path seen.
    """

    def __init__(
        self,
        app: ASGIApp,
        base_url: str,
        secret_key: str,
        session_cookie: str,
        max_age: int,
        same_site: Literal["lax", "strict", "none"],
        https_only: bool,
    ) -> None:
        self.app = app
        self.base_url = base_url
        self.secret_key = secret_key
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.same_site = same_site
        self.https_only = https_only
        self._scoped: dict[str, SessionMiddleware] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        root_path = scope.get("root_path", "")
        middleware = self._scoped.get(root_path)
        if middleware is None:
            middleware = SessionMiddleware(
                self.app,
                secret_key=self.secret_key,
                session_cookie=self.session_cookie,
                path=admin_cookie_path(root_path, self.base_url),
                max_age=self.max_age,
                same_site=self.same_site,
                https_only=self.https_only,
            )
            self._scoped[root_path] = middleware

        await middleware(scope, receive, send)


def _credential_matches(submitted: object, expected: str) -> bool:
    """Compare a submitted credential against the configured one in constant time."""
    if not isinstance(submitted, str):
        return False
    return hmac.compare_digest(submitted.encode(), expected.encode())


class AdminAuth(AuthenticationBackend):
    """Session-based authentication for the admin interface.

    The panel mounts its own session middleware, which is the only one that cookie
    needs. The cookie is scoped to where the panel is mounted, prefix included, is
    HTTPS-only outside local and development, and expires after
    ``SESSION_MAX_AGE_SECONDS`` rather than Starlette's fortnight.
    """

    def __init__(self, secret_key: str, base_url: str | None = None) -> None:
        super().__init__(secret_key)
        settings = get_settings()
        local = settings.ENVIRONMENT in (EnvironmentOption.LOCAL, EnvironmentOption.DEVELOPMENT)

        self.middlewares = [
            Middleware(
                RootPathSessionMiddleware,
                base_url=base_url or admin_base_url(),
                secret_key=secret_key,
                session_cookie="admin_session",
                max_age=SESSION_MAX_AGE_SECONDS,
                same_site="lax",
                https_only=not local,
            )
        ]

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
