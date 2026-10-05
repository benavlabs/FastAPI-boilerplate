"""crudauth composition root.

A single module-level ``auth`` singleton wired over the existing ``User`` model.
It is constructed here, not in the lifespan, because routers and ``current_user``
dependencies reference it at import time; the lifespan only opens and closes its
connections via ``auth.initialize()`` / ``auth.shutdown()`` (see ``app_factory``).

Wires a single session transport (sessions + CSRF + escalating login lockout)
over the configured session backend, the limiter behind the login lockout, the
password policy, and Google OAuth when it's configured. Email recovery and sudo are intentionally not configured - the
boilerplate has no email pipeline, and no route gates on sudo.
"""

from typing import Any

from crudauth import CookieConfig, CRUDAuth, NewUserContext, OAuthCredentials, SessionTransport
from crudauth.ratelimit import LockoutConfig

from ...modules.user.constants import NAME_MAX_LENGTH
from ...modules.user.models import User
from ..composition import Lifecycle
from ..config.enums import SessionBackend
from ..config.settings import settings
from ..database.session import async_session
from .limiter import build_rate_limiter, rate_limiter_redis_client
from .password_policy import password_policy

OAUTH_PREFIX = f"{settings.API_PREFIX}/v1/auth/oauth"


def _session_transport() -> SessionTransport:
    """Cookie sessions on ``SESSION_BACKEND``, on their own Redis database when Redis-backed."""
    use_redis = settings.SESSION_BACKEND == SessionBackend.REDIS
    return SessionTransport(
        backend=SessionBackend.REDIS.value if use_redis else SessionBackend.MEMORY.value,
        redis_url=settings.SESSION_REDIS_URL if use_redis else None,
        csrf=settings.CSRF_ENABLED,
        max_sessions_per_user=settings.MAX_SESSIONS_PER_USER,
        session_timeout_minutes=settings.SESSION_TIMEOUT_MINUTES,
        cleanup_interval_minutes=settings.SESSION_CLEANUP_INTERVAL_MINUTES,
    )


def _new_user_fields(context: NewUserContext) -> dict[str, Any]:
    """The columns crudauth doesn't fill for an account it creates: the display name."""
    return {"name": context.suggested_name[:NAME_MAX_LENGTH]}


def _oauth_providers() -> dict[str, OAuthCredentials]:
    if settings.OAUTH_GOOGLE_CLIENT_ID and settings.OAUTH_GOOGLE_CLIENT_SECRET:
        return {
            "google": OAuthCredentials(
                client_id=settings.OAUTH_GOOGLE_CLIENT_ID,
                client_secret=settings.OAUTH_GOOGLE_CLIENT_SECRET,
            )
        }
    return {}


session_transport = _session_transport()

auth = CRUDAuth(
    session=async_session,
    user_model=User,
    SECRET_KEY=settings.SECRET_KEY,
    cookies=CookieConfig(secure=settings.SESSION_SECURE_COOKIES),
    transports=[session_transport],
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
