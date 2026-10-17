"""Authentication backend for SQLAdmin."""

import hashlib
import hmac
from time import time
from typing import Any, Literal

from crudauth import HookContext
from crudauth.utils import get_client_ip
from sqladmin.authentication import AuthenticationBackend
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from ...infrastructure.auth.audit import log_a_lockout, log_a_refusal
from ...infrastructure.config.settings import EnvironmentOption, get_settings
from ...infrastructure.logging import get_logger
from .lockout import every_address_lockout, panel_lockout
from .origin import SameOriginOnly

logger = get_logger()

SESSION_MAX_AGE_SECONDS = 60 * 60 * 8

AUTHENTICATED = "admin_authenticated"
"""The session key a signed-in operator carries."""

ISSUED_AT = "issued_at"
"""When the login that created the session happened, in seconds since the epoch."""

FINGERPRINT = "fingerprint"
"""An HMAC of the credentials the session was created against."""

LOCKOUT_PREFIX = "admin-panel"
"""Prefix of the identifier the per-address lockout counts the panel's failures against."""

EVERY_ADDRESS = "every-address"
"""The identifier the panel-wide lockout counts every failure against, whatever address sent it."""

DOOR = "the admin panel"
"""The panel, as the audit log names it."""

EVERY_ADDRESS_DOOR = f"{DOOR} (every address)"
"""The panel-wide lockout, as the audit log names it, apart from one address's."""


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
    needs, behind a guard that refuses an unsafe method from another origin. The cookie is
    scoped to where the panel is mounted, prefix included, is HTTPS-only outside local and
    development, travels on nothing a sibling site starts (``SameSite=Strict``), and
    expires after ``SESSION_MAX_AGE_SECONDS`` rather than Starlette's fortnight.

    The session itself carries when it was issued and a fingerprint of the credentials it
    was issued against, which is what bounds it: see
    [authenticate][src.interfaces.admin.auth.AdminAuth.authenticate].
    """

    def __init__(self, secret_key: str, base_url: str | None = None) -> None:
        super().__init__(secret_key)
        self.secret_key = secret_key
        settings = get_settings()
        local = settings.ENVIRONMENT in (EnvironmentOption.LOCAL, EnvironmentOption.DEVELOPMENT)

        self.middlewares = [
            Middleware(SameOriginOnly),
            Middleware(
                RootPathSessionMiddleware,
                base_url=base_url or admin_base_url(),
                secret_key=secret_key,
                session_cookie="admin_session",
                max_age=SESSION_MAX_AGE_SECONDS,
                same_site="strict",
                https_only=not local,
            ),
        ]

    async def login(self, request: Request) -> bool:
        """Validate login credentials and create session.

        Failures are counted on two lockouts of the panel's own, both in a key space the
        public login API cannot write by submitting their identifiers as a username. One
        counts the client address, against the identifier ``admin-panel:<address>``. The
        other counts every failure the panel refuses, whatever address it came from, so a
        caller changing address runs out of guesses too. A locked caller is refused before
        the submitted password is compared.

        A login that succeeds clears what its address was counted and gives back the one
        attempt it made against every address, leaving the failures that came from
        elsewhere counted.
        """
        settings = get_settings()

        if not settings.ADMIN_USERNAME or not settings.ADMIN_PASSWORD:
            return False

        address = get_client_ip(request, settings.TRUSTED_PROXY_HOPS)
        caller = HookContext(ip_address=address, user_agent=request.headers.get("user-agent"))
        counted_against = f"{LOCKOUT_PREFIX}:{address}"

        if panel_lockout is not None:
            allowed, _remaining, retry_after = await panel_lockout.check_and_record(address, counted_against)
            if not allowed:
                await log_a_lockout(DOOR, retry_after=retry_after, context=caller)
                return False

        if every_address_lockout is not None:
            allowed, _remaining, retry_after = await every_address_lockout.check_and_record(EVERY_ADDRESS, EVERY_ADDRESS)
            if not allowed:
                await log_a_lockout(EVERY_ADDRESS_DOOR, retry_after=retry_after, context=caller)
                return False

        form = await request.form()
        submitted = form.get("username")
        username_matches = _credential_matches(submitted, settings.ADMIN_USERNAME)
        password_matches = _credential_matches(form.get("password"), settings.ADMIN_PASSWORD)

        if username_matches and password_matches:
            if panel_lockout is not None:
                await panel_lockout.check_and_record(address, counted_against, success=True)
            if every_address_lockout is not None:
                await every_address_lockout.forget_attempt(EVERY_ADDRESS, EVERY_ADDRESS)
            request.session.update(
                {
                    AUTHENTICATED: True,
                    ISSUED_AT: int(time()),
                    FINGERPRINT: self.credentials_fingerprint(),
                }
            )
            return True

        await log_a_refusal(
            DOOR,
            submitted if isinstance(submitted, str) else "",
            known=username_matches,
            reason="invalid_credentials",
            context=caller,
        )
        return False

    async def logout(self, request: Request) -> bool:
        """Clear the admin session."""
        request.session.clear()
        return True

    def credentials_fingerprint(self) -> str:
        """An HMAC of the configured credentials, which changing either one of them changes.

        Keyed with ``SECRET_KEY``, because the session travels in a cookie the browser can
        read: a plain digest of the password would be one an attacker holding the cookie
        could work backwards from.
        """
        settings = get_settings()
        credentials = f"{settings.ADMIN_USERNAME}:{settings.ADMIN_PASSWORD}".encode()

        return hmac.new(self.secret_key.encode(), credentials, hashlib.sha256).hexdigest()

    def _refuse(self, session: dict[str, Any], why: str) -> bool:
        """Clear the session the request carried, so the browser stops sending it."""
        session.clear()
        logger.warning(f"admin session refused: {why}")

        return False

    async def authenticate(self, request: Request) -> bool:
        """Whether the request carries a session the panel still honours.

        A session is honoured for ``SESSION_MAX_AGE_SECONDS`` from the login that created
        it, however busy the operator has been in between. Starlette re-signs the cookie
        whenever something writes to the session, a flashed message included, which starts
        its ``Max-Age`` and its signature's clock again; the cap is ``issued_at``, which
        nothing moves.

        A session is also refused once ``ADMIN_USERNAME`` or ``ADMIN_PASSWORD`` changes,
        which the fingerprint it carries no longer matches, so changing either signs out
        every session including a stolen one. A session from before either was recorded is
        refused too.
        """
        session = request.session
        if not session.get(AUTHENTICATED, False):
            return False

        issued_at = session.get(ISSUED_AT)
        if not isinstance(issued_at, int | float) or time() - issued_at >= SESSION_MAX_AGE_SECONDS:
            return self._refuse(session, "issued longer ago than the panel honours a session")

        if not hmac.compare_digest(str(session.get(FINGERPRINT, "")), self.credentials_fingerprint()):
            return self._refuse(session, "issued against credentials that have since changed")

        return True
