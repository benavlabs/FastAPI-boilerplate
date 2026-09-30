"""Counting a password check against crudauth's change-password budget."""

from crudauth.ratelimit.dependency import enforce_rate_limit
from fastapi import Request, Response

from .setup import auth

PASSWORD_ATTEMPT_ACTION = "change_password"


async def count_password_attempt(request: Request, user_id: int) -> None:
    """Count one password check for ``user_id``, answering 429 past the configured budget.

    The headers the limiter computes go to a response of their own, so the caller's
    reply keeps the ones the API throttle wrote.

    Raises:
        RateLimitException: The account has spent its budget for the window.
    """
    await enforce_rate_limit(
        auth.rate_limiter,
        request,
        Response(),
        action=PASSWORD_ATTEMPT_ACTION,
        identity=str(user_id),
        limit=auth.rate_limits[PASSWORD_ATTEMPT_ACTION],
    )
