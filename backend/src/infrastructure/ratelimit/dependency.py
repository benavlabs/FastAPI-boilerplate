"""The API throttle: one budget per caller per path, sized by the first resolver that answers.

Resolvers are contributed by other features -- the tier-limits feature answers
with the caller's tier row -- and listed in ``wiring.hooks``. With no resolver
answering, the default limit from settings applies.
"""

from crudauth import Principal
from crudauth.ratelimit import RateLimit
from crudauth.utils import client_ip_key, get_client_ip
from fastapi import Request

from ...wiring.hooks import RATE_LIMIT_RESOLVERS
from ..auth.setup import auth
from ..config.settings import settings


def api_rate_limit_key(request: Request, principal: Principal | None) -> str:
    """Name the budget a request counts against: one per caller per path.

    Limits are configured per path, so each path keeps its own counter: spending
    the budget on one route never throttles another.
    """
    if principal is not None:
        caller = f"user:{principal.user_id}"
    else:
        caller = f"ip:{client_ip_key(get_client_ip(request, settings.TRUSTED_PROXY_HOPS))}"

    return f"{caller}:{request.url.path}"


async def resolve_api_rate_limit(request: Request, principal: Principal | None) -> RateLimit | None:
    """The limit for this request: the first contributed resolver's answer, else the default."""
    if not settings.RATE_LIMITER_ENABLED:
        return None

    for resolver in RATE_LIMIT_RESOLVERS:
        limit = await resolver(request, principal)
        if limit is not None:
            return limit

    return RateLimit(settings.DEFAULT_RATE_LIMIT_LIMIT, settings.DEFAULT_RATE_LIMIT_PERIOD)


api_rate_limit_dependency = auth.rate_limit("api", resolve_api_rate_limit, key=api_rate_limit_key)
