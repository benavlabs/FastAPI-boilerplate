"""The API throttle: one budget per caller per path, sized by the first resolver that answers.

Resolvers are contributed by other features -- the tier-limits feature answers
with the caller's tier row -- and listed in ``wiring.hooks``. With no resolver
answering, the default limit from settings applies.
"""

from crudauth import Principal
from crudauth.exceptions import UnauthorizedException
from crudauth.ratelimit import RateLimit
from crudauth.ratelimit.dependency import enforce_rate_limit
from crudauth.utils import client_ip_key, get_client_ip
from fastapi import Request, Response

from ...wiring.hooks import RATE_LIMIT_RESOLVERS
from ..auth.setup import auth
from ..config.settings import settings
from ..dependencies import AsyncSessionDep
from .routing import throttled_path

API_ACTION = "api"
"""The action the API throttle counts under, shared by the dependency and the refusal below."""


def api_rate_limit_key(request: Request, principal: Principal | None) -> str:
    """Name the budget a request counts against: one per caller per route.

    Limits are configured per route, so each route keeps its own counter: spending
    the budget on one never throttles another.
    """
    if principal is not None:
        caller = f"user:{principal.user_id}"
    else:
        caller = f"ip:{client_ip_key(get_client_ip(request, settings.TRUSTED_PROXY_HOPS))}"

    return f"{caller}:{throttled_path(request)}"


async def resolve_api_rate_limit(request: Request, principal: Principal | None) -> RateLimit | None:
    """The limit for this request: the first contributed resolver's answer, else the default."""
    if not settings.RATE_LIMITER_ENABLED:
        return None

    for resolver in RATE_LIMIT_RESOLVERS:
        limit = await resolver(request, principal)
        if limit is not None:
            return limit

    return RateLimit(settings.DEFAULT_RATE_LIMIT_LIMIT, settings.DEFAULT_RATE_LIMIT_PERIOD)


_throttle = auth.rate_limit(API_ACTION, resolve_api_rate_limit, key=api_rate_limit_key)


async def api_rate_limit_dependency(request: Request, response: Response, db: AsyncSessionDep) -> None:
    """Throttle this request, counting a credential that doesn't resolve against its address.

    A credential that does not resolve spends the budget an anonymous caller from the same
    address spends on this path: the budget the request would have had carrying none. A
    caller whose credential resolves keeps a budget of their own.

    Raises:
        RateLimitException: The caller has filled the window for this path.
        UnauthorizedException: The credential the request carried does not resolve.
    """
    try:
        await _throttle(request, response, db)
    except UnauthorizedException:
        await enforce_rate_limit(
            auth.rate_limiter,
            request,
            response,
            action=API_ACTION,
            identity=api_rate_limit_key(request, None),
            limit=resolve_api_rate_limit,
        )
        raise
