"""The ``X-API-Key`` transport: a request authenticated by a key, as the key's owner."""

import time
from dataclasses import replace
from typing import NamedTuple

from crudauth import AuthContext, Principal, Transport
from crudauth.exceptions import RateLimitException, UnauthorizedException
from crudauth.ratelimit import RateLimiterBackend
from crudauth.utils import get_client_ip
from starlette.requests import Request

from ...infrastructure.auth.scope import SCOPE_OWNER_IS_SUPERUSER
from .limits import (
    REFUSALS_RECORDED_PER_WINDOW,
    WINDOWS,
    counted_shortest_first,
    counter_key,
    refusal_key,
    time_left,
    window_stamped,
)
from .service import APIKeyService

API_KEY_HEADER = "X-API-Key"
TRANSPORT_NAME = "apikey"

INVALID_KEY = "Invalid API key"
RECOVERED_ACCOUNT = "This API key was issued before the account was recovered."
OVER_THE_LIMIT = "This API key has made too many requests."


class Refusal(NamedTuple):
    """A request one of a key's windows turned away, and whether it is the one recorded."""

    retry_after: int
    recorded: bool


class UsedKey(NamedTuple):
    """The key a request was authenticated with, and the address it came from."""

    api_key_id: int
    owner_id: int
    client_ip: str | None


def used_key(request: Request) -> UsedKey | None:
    """What this request was authenticated with, or ``None`` when no key was.

    Stamped by the transport, so anything running after the handler — the usage
    recorder — names the key, and the same address the transport resolved, without
    doing either again.
    """
    api_key_id = getattr(request.state, "api_key_id", None)
    owner_id = getattr(request.state, "api_key_user_id", None)
    if api_key_id is None or owner_id is None:
        return None

    return UsedKey(api_key_id, owner_id, getattr(request.state, "api_key_client_ip", None))


class APIKeyTransport(Transport):
    """Authenticates a request by the key its ``X-API-Key`` header carries.

    A request without the header carries no credential here, so the facade moves on to
    the next transport. A header that carries anything else answers 401: a key that is
    unknown, revoked, expired, whose row holds a column no schema can read, or whose owner
    a soft delete has taken out.

    The principal carries the key's scope, which narrows what its owner holds, and never
    the owner's superuser flag: that flag reaches ownership checks no scope can express,
    so it is recorded in the metadata for the narrowing to read and nothing else.

    A key is refused once its owner's credential generation has moved past the one it was
    minted under. Claiming an account through a provider, resetting its password and
    changing it each bump that generation, so recovering an account takes its keys back
    with it. Ending sessions does not: a key holds none.

    A key over one of its ``usage_limits`` answers 429 here rather than at a route, so
    every route a key can reach is covered, throttled or not. The first refusal a window
    answers is stamped with the key, so the usage recorder writes it; the rest are stamped
    with nothing, and a key held at its limit costs the limiter alone.
    """

    name = TRANSPORT_NAME

    def __init__(self, service: APIKeyService | None = None) -> None:
        self._service = service or APIKeyService()

    async def authenticate(self, request: Request, ctx: AuthContext) -> Principal | None:
        """The owner of the key the header carries, or ``None`` when it carries none."""
        presented = request.headers.get(API_KEY_HEADER)
        if not presented:
            return None

        validated = await self._service.validate_api_key(api_key=presented, db=ctx.db)
        owner = await ctx.resolve_user(validated.user_id) if validated.is_valid else None
        if owner is None or not ctx.repo.is_active(owner):
            raise UnauthorizedException(INVALID_KEY)

        if validated.owner_token_version != ctx.repo.token_version(owner):
            raise UnauthorizedException(RECOVERED_ACCOUNT)

        refusal = await self._refusal(validated.api_key_id, validated.usage_limits or {}, ctx)
        if refusal is None or refusal.recorded:
            request.state.api_key_id = validated.api_key_id
            request.state.api_key_user_id = validated.user_id
            request.state.api_key_client_ip = get_client_ip(request, ctx.runtime.trusted_proxy_hops)

        if refusal is not None:
            raise RateLimitException(OVER_THE_LIMIT, retry_after=refusal.retry_after)

        principal = ctx.build_principal(
            user_id=ctx.repo.user_id(owner),
            user=owner,
            transport=self.name,
            scopes=tuple(validated.permissions or ()),
            metadata={
                "api_key_id": validated.api_key_id,
                SCOPE_OWNER_IS_SUPERUSER: ctx.repo.is_superuser(owner),
            },
        )

        return replace(principal, is_superuser=False)

    async def _refusal(self, api_key_id: int | None, limits: dict[str, int], ctx: AuthContext) -> Refusal | None:
        """Count this request against each window the key carries, naming one it fills.

        Counting fails open: a limiter that can't be reached must not take the API down
        with it, the way the login lockout deliberately fails closed. A stored limit
        naming a window nothing counts is skipped rather than raised over.

        The windows are counted shortest first, so a request refused by one of them has
        spent nothing in the longer ones: a key at its per-minute limit keeps its day.

        A window's refusals are counted of their own, and the first of them is the one the
        recorder is given, so a key held at its limit writes a row a window rather than a
        row a request.

        Returns:
            The window's refusal, or ``None`` where the request filled no window.
        """
        limiter = ctx.runtime.rate_limiter
        if api_key_id is None or limiter is None or not limits:
            return None

        counted = counted_shortest_first(limits)
        for position, (window, allowed) in enumerate(counted):
            _, over, retry_after = await limiter.increment_and_check(
                counter_key(api_key_id, window), allowed, WINDOWS[window], fail_open=True
            )
            if over:
                held = await self._filled_longest(limiter, api_key_id, counted[position + 1 :])
                _, already, _ = await limiter.increment_and_check(
                    refusal_key(api_key_id, window), REFUSALS_RECORDED_PER_WINDOW, WINDOWS[window], fail_open=True
                )

                return Refusal(max(retry_after, held), not already)

        return None

    async def _filled_longest(self, limiter: RateLimiterBackend, api_key_id: int, longer: list[tuple[str, int]]) -> int:
        """How long until the last of the longer windows the key has filled rolls, or ``0`` for none.

        The request being refused never reached these windows, so they are read and never
        counted. Naming the window that refused would send a client back the moment that
        one rolls, to be refused again by a longer window it cannot wait out that way, so
        what is named is the longest window a request coming back would still be refused
        by. A read that fails leaves its window out, the way a count that fails lets a
        request through.
        """
        now = int(time.time())
        longest = 0
        for window, allowed in longer:
            seconds = WINDOWS[window]
            try:
                filled = await limiter.get_count(window_stamped(counter_key(api_key_id, window), seconds, now)) or 0
            except Exception:
                continue

            if filled >= allowed:
                longest = max(longest, time_left(seconds, now))

        return longest
