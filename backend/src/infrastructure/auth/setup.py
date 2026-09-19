"""crudauth composition root.

A single module-level ``auth`` singleton wired over the existing ``User`` model.
It is constructed here, not in the lifespan, because routers and ``current_user``
dependencies reference it at import time; the lifespan only opens and closes its
connections via ``auth.initialize()`` / ``auth.shutdown()`` (see ``app_factory``).

Wires a single session transport (sessions + CSRF + escalating login lockout)
over the configured session backend, the rate limiter behind both the login
lockout and the per-tier API limits, the password policy, and Google OAuth when
it's configured. Email recovery and sudo are intentionally not configured - the
boilerplate has no email pipeline, and no route gates on sudo.
"""

from contextlib import asynccontextmanager
from typing import Any

from crudauth import CookieConfig, CRUDAuth, NewUserContext, OAuthCredentials, Principal, SessionTransport
from crudauth.ratelimit import RateLimit, RateLimiterBackend, redis_rate_limiter
from crudauth.utils import client_ip_key, get_client_ip
from fastapi import Request

from ...modules.rate_limit.crud import crud_rate_limits
from ...modules.rate_limit.schemas import RateLimitSelect
from ...modules.user.constants import NAME_MAX_LENGTH
from ...modules.user.models import User
from ..config.enums import RateLimiterBackend as RateLimiterBackendName
from ..config.enums import SessionBackend
from ..config.settings import settings
from ..database.session import async_session
from ..redis import rate_limiter_redis_client
from .password_policy import password_policy

OAUTH_PREFIX = "/api/v1/auth/oauth"


def _rate_limiter() -> RateLimiterBackend | None:
    """The limiter backend ``RATE_LIMITER_BACKEND`` names; ``None`` lets crudauth use memory."""
    backend = settings.RATE_LIMITER_BACKEND
    if backend == RateLimiterBackendName.REDIS:
        return redis_rate_limiter(client=rate_limiter_redis_client)
    if backend == RateLimiterBackendName.MEMORY:
        return None
    raise ValueError(
        f"RATE_LIMITER_BACKEND={backend!r} isn't supported; use 'redis' or 'memory'. "
        "The memcached rate limiter was removed when rate limiting moved to crudauth."
    )


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


auth = CRUDAuth(
    session=async_session,
    user_model=User,
    SECRET_KEY=settings.SECRET_KEY,
    cookies=CookieConfig(secure=settings.SESSION_SECURE_COOKIES),
    transports=[_session_transport()],
    rate_limiter=_rate_limiter(),
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


def api_rate_limit_key(request: Request, principal: Principal | None) -> str:
    """Name the budget a request counts against: one per caller per path.

    Tier limits are configured per path, so each path keeps its own counter -
    spending the budget on one route never throttles another.
    """
    if principal is not None:
        caller = f"user:{principal.user_id}"
    else:
        caller = f"ip:{client_ip_key(get_client_ip(request, settings.TRUSTED_PROXY_HOPS))}"
    return f"{caller}:{request.url.path}"


async def resolve_api_rate_limit(request: Request, principal: Principal | None) -> RateLimit | None:
    """The limit for this request: the caller's tier row for the path, else the default.

    The row is read through the app's own database dependency, honoring any
    override on it, so the lookup uses the same database as the route it guards.
    """
    if not settings.RATE_LIMITER_ENABLED:
        return None

    tier_id: Any = auth.repo.get(principal.user, "tier_id") if principal is not None and principal.user else None
    if tier_id is not None:
        database = request.app.dependency_overrides.get(async_session, async_session)
        async with asynccontextmanager(database)() as db:
            configured = await crud_rate_limits.get(
                db=db, tier_id=tier_id, path=request.url.path, schema_to_select=RateLimitSelect
            )
        if configured:
            return RateLimit(configured["limit"], configured["period"])

    return RateLimit(settings.DEFAULT_RATE_LIMIT_LIMIT, settings.DEFAULT_RATE_LIMIT_PERIOD)


api_rate_limit_dependency = auth.rate_limit("api", resolve_api_rate_limit, key=api_rate_limit_key)
