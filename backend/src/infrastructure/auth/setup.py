"""crudauth composition root.

A single module-level ``auth`` singleton wired over the existing ``User`` model.
It is constructed here, not in the lifespan, because routers and ``current_user``
dependencies reference it at import time; the lifespan only opens and closes its
connections via ``auth.initialize()`` / ``auth.shutdown()`` (see ``app_factory``).

Wires the session transport (sessions + CSRF + escalating login lockout) over the
configured session backend, whatever other transports the wiring selected, the limiter
behind the login lockout, the password policy, the email recovery flows over the sender the
wiring chose, and every OAuth provider whose credentials are configured. The session
transport comes first, so a request carrying both a cookie and another credential is its
session. Sudo is intentionally not configured: no route gates on it.
"""

from typing import Any

from crudauth import CookieConfig, CRUDAuth, EmailConfig, NewUserContext, OAuthCredentials, SessionTransport
from crudauth.ratelimit import LockoutConfig

from ...modules.user.constants import NAME_MAX_LENGTH
from ...modules.user.models import User
from ...wiring.email import EMAIL_SENDER
from ...wiring.transports import EXTRA_TRANSPORTS
from ..composition import Lifecycle
from ..config.enums import SessionBackend
from ..config.settings import settings
from ..database.session import async_session
from .limiter import build_rate_limiter, rate_limiter_redis_client
from .password_policy import password_policy

OAUTH_PREFIX = f"{settings.API_PREFIX}/v1/auth/oauth"
OAUTH_PROVIDERS = ("google", "github")
"""The providers this project reads credentials for, each named as crudauth registers it."""


def _absolute_timeout_hours() -> int | None:
    """``SESSION_ABSOLUTE_TIMEOUT_HOURS``, or ``None`` where no cap is configured.

    Raises:
        ValueError: The setting is below one hour, which would expire every session as
            soon as it was created.
    """
    hours = settings.SESSION_ABSOLUTE_TIMEOUT_HOURS
    if hours is not None and hours < 1:
        raise ValueError(f"SESSION_ABSOLUTE_TIMEOUT_HOURS={hours!r} isn't supported; leave it unset for no cap.")

    return hours


def _session_transport() -> SessionTransport:
    """Cookie sessions on ``SESSION_BACKEND``, on their own Redis database when Redis-backed."""
    use_redis = settings.SESSION_BACKEND == SessionBackend.REDIS
    return SessionTransport(
        backend=SessionBackend.REDIS.value if use_redis else SessionBackend.MEMORY.value,
        redis_url=settings.SESSION_REDIS_URL if use_redis else None,
        csrf=settings.CSRF_ENABLED,
        max_sessions_per_user=settings.MAX_SESSIONS_PER_USER,
        session_timeout_minutes=settings.SESSION_TIMEOUT_MINUTES,
        absolute_timeout_hours=_absolute_timeout_hours(),
        cleanup_interval_minutes=settings.SESSION_CLEANUP_INTERVAL_MINUTES,
    )


def _new_user_fields(context: NewUserContext) -> dict[str, Any]:
    """The columns crudauth doesn't fill for an account it creates: the display name."""
    return {"name": context.suggested_name[:NAME_MAX_LENGTH]}


def _oauth_providers() -> dict[str, OAuthCredentials]:
    """Every provider crudauth ships whose client id and secret are both configured."""
    configured = {}
    for provider in OAUTH_PROVIDERS:
        client_id = getattr(settings, f"OAUTH_{provider.upper()}_CLIENT_ID")
        client_secret = getattr(settings, f"OAUTH_{provider.upper()}_CLIENT_SECRET")
        if client_id and client_secret:
            configured[provider] = OAuthCredentials(client_id=client_id, client_secret=client_secret)

    return configured


session_transport = _session_transport()
email_config = EmailConfig(sender=EMAIL_SENDER, frontend_url=settings.FRONTEND_URL.rstrip("/"))

auth = CRUDAuth(
    session=async_session,
    user_model=User,
    SECRET_KEY=settings.SECRET_KEY,
    cookies=CookieConfig(secure=settings.SESSION_SECURE_COOKIES),
    transports=[session_transport, *EXTRA_TRANSPORTS],
    rate_limiter=build_rate_limiter(),
    lockout=LockoutConfig(
        max_attempts=settings.LOGIN_MAX_ATTEMPTS,
        attempt_window_seconds=settings.LOGIN_ATTEMPT_WINDOW_SECONDS,
        lockout_base_seconds=settings.LOGIN_LOCKOUT_BASE_SECONDS,
        lockout_max_seconds=settings.LOGIN_LOCKOUT_MAX_SECONDS,
    ),
    trusted_proxy_hops=settings.TRUSTED_PROXY_HOPS,
    password_policy=password_policy,
    new_user_fields=_new_user_fields,
    email=email_config,
    oauth=_oauth_providers() or None,
    redirect_base_url=settings.OAUTH_REDIRECT_BASE_URL.rstrip("/"),
    oauth_paths={
        "prefix": OAUTH_PREFIX,
        "authorize_path": "/{provider}",
        "callback_path": "/callback/{provider}",
    },
    oauth_response_mode="redirect",
)


async def _close_limiter_client() -> None:
    await rate_limiter_redis_client.aclose()


lifecycle = Lifecycle("accounts", startup=auth.initialize, shutdown=(auth.shutdown, _close_limiter_client))
