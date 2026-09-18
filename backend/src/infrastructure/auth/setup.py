"""crudauth composition root.

A single module-level ``auth`` singleton wired over the existing ``User`` model.
It is constructed here, not in the lifespan, because routers and ``current_user``
dependencies reference it at import time; the lifespan only opens and closes its
connections via ``auth.initialize()`` / ``auth.shutdown()`` (see ``app_factory``).

Wires a single session transport (sessions + CSRF + escalating login lockout)
over the configured session backend, plus a shared Redis rate limiter for the
lockout counters. Email recovery and sudo are intentionally not configured -
the boilerplate has no email pipeline, and no route gates on sudo.
"""

from crudauth import CookieConfig, CRUDAuth, OAuthCredentials, PasswordPolicy, Principal, SessionTransport
from crudauth.ratelimit import KeyBy, RateLimit, redis_rate_limiter
from fastapi import Request

from ...modules.rate_limit.crud import crud_rate_limits
from ...modules.rate_limit.schemas import RateLimitSelect
from ...modules.tier.crud import crud_tiers
from ...modules.tier.schemas import TierSelect
from ...modules.user.models import User
from ..config.settings import settings
from ..database.session import async_session, local_session
from ..redis import rate_limiter_redis_client

_session_redis_url = settings.SESSION_REDIS_URL

_use_redis = settings.SESSION_BACKEND == "redis"
_oauth = {}
if settings.OAUTH_GOOGLE_CLIENT_ID and settings.OAUTH_GOOGLE_CLIENT_SECRET:
    _oauth["google"] = OAuthCredentials(
        client_id=settings.OAUTH_GOOGLE_CLIENT_ID,
        client_secret=settings.OAUTH_GOOGLE_CLIENT_SECRET,
    )

auth = CRUDAuth(
    session=async_session,
    user_model=User,
    SECRET_KEY=settings.SECRET_KEY,
    cookies=CookieConfig(secure=settings.SESSION_SECURE_COOKIES),
    transports=[
        SessionTransport(
            backend="redis" if _use_redis else "memory",
            redis_url=_session_redis_url if _use_redis else None,
            csrf=settings.CSRF_ENABLED,
            max_sessions_per_user=settings.MAX_SESSIONS_PER_USER,
            session_timeout_minutes=settings.SESSION_TIMEOUT_MINUTES,
            cleanup_interval_minutes=settings.SESSION_CLEANUP_INTERVAL_MINUTES,
        )
    ],
    rate_limiter=redis_rate_limiter(client=rate_limiter_redis_client) if settings.RATE_LIMITER_ENABLED and _use_redis else None,
    trusted_proxy_hops=settings.TRUSTED_PROXY_HOPS,
    password_policy=PasswordPolicy(
        min_length=settings.PASSWORD_MIN_LENGTH,
        require_uppercase=settings.PASSWORD_REQUIRE_UPPERCASE,
        require_lowercase=settings.PASSWORD_REQUIRE_LOWERCASE,
        require_digit=settings.PASSWORD_REQUIRE_DIGIT,
        require_special=settings.PASSWORD_REQUIRE_SPECIAL,
    ),
    oauth=_oauth or None,
    redirect_base_url=settings.OAUTH_REDIRECT_BASE_URL,
    oauth_paths={
        "prefix": "/oauth",
        "authorize_path": "/{provider}",
        "callback_path": "/callback/{provider}",
    },
    oauth_response_mode="json",
)


async def resolve_api_rate_limit(request: Request, principal: Principal | None) -> RateLimit | None:
    """Resolve the configured tier/path limit for crudauth's limiter."""
    if not settings.RATE_LIMITER_ENABLED:
        return None

    async with local_session() as db:
        tier_id = auth.repo.get(principal.user, "tier_id") if principal and principal.user else None
        if tier_id is not None:
            tier = await crud_tiers.get(db=db, id=tier_id, schema_to_select=TierSelect)
            if tier:
                configured = await crud_rate_limits.get(
                    db=db, tier_id=tier["id"], path=request.url.path, schema_to_select=RateLimitSelect
                )
                if configured:
                    return RateLimit(configured["limit"], configured["period"])

    return RateLimit(settings.DEFAULT_RATE_LIMIT_LIMIT, settings.DEFAULT_RATE_LIMIT_PERIOD)


api_rate_limit_dependency = auth.rate_limit("api", resolve_api_rate_limit, key=KeyBy.USER_OR_IP)
