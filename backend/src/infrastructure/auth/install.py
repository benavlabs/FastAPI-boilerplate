"""App-level wiring for accounts."""

from crudauth.ratelimit import RateLimitHeadersMiddleware
from fastapi import FastAPI


def install(app: FastAPI) -> None:
    """Report crudauth's limits on responses: ``X-RateLimit-*`` and ``Retry-After``.

    The login lockout runs whether or not API routes are throttled, so its
    headers are worth sending either way.
    """
    app.add_middleware(RateLimitHeadersMiddleware)
