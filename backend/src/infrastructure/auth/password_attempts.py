"""Counting a password check against crudauth's change-password budget."""

from crudauth.ratelimit.dependency import enforce_rate_limit
from fastapi import Request, Response

from .setup import auth

PASSWORD_ATTEMPT_ACTION = "change_password"


async def count_password_attempt(request: Request, user_id: int) -> None:
    """Count one password check for ``user_id``, answering 429 past the configured budget.

    The limiter records its headers on a request and a response of its own; its 429
    carries them itself.

    Raises:
        RateLimitException: The account has spent its budget for the window.
    """
    counted = Request({**request.scope, "state": {}}, request.receive)

    await enforce_rate_limit(
        auth.rate_limiter,
        counted,
        Response(),
        action=PASSWORD_ATTEMPT_ACTION,
        identity=str(user_id),
        limit=auth.rate_limits[PASSWORD_ATTEMPT_ACTION],
    )
