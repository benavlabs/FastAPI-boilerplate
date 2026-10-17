"""Refusing a panel request a browser says came from somewhere else.

sqladmin has no CSRF token, so what stands between a signed-in operator and another site
driving the panel is the admin cookie's ``SameSite`` and this guard: a request that may
change something is refused unless the browser's ``Sec-Fetch-Site`` says it came from the
panel's own origin, or its ``Origin`` names the host the request arrived at.
``SameSite=Lax`` alone leaves a sibling subdomain, and script on a same-site frontend,
able to post to the panel; ``Strict`` does not help against a sibling, which is the same
site as far as a browser is concerned, so the cookie travels on its links either way.

A request carrying neither header is allowed, which is what keeps curl and scripts
working: no site can make a browser send a request with no origin at all.
"""

import re
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ...infrastructure.logging import get_logger

logger = get_logger()

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
"""Methods that change nothing, which a cross-origin caller may use."""

OWN_ORIGIN_SITES = frozenset({"same-origin", "none"})
"""The ``Sec-Fetch-Site`` values that mean the panel's own pages, or no site at all."""

ACTION_PATH = re.compile(r"^/[^/]+/action/[^/]+/?$")
"""Where sqladmin serves a ``@action`` under the panel's mount: ``/{identity}/action/{slug}``."""


def changes_state(method: str, path: str) -> bool:
    """Whether this request may change something, whatever its method says.

    An unsafe method may. So may a ``GET`` of an action route: sqladmin registers every
    ``@action`` on one, and the panel's own pages reach them through plain links, which
    anything that can navigate the operator's browser can send too.

    Args:
        method: The request's method.
        path: The path under the panel's mount, which is what the action routes are named
            against: a model of its own called ``Action`` keeps its ``/action/list`` read.
    """
    if method not in SAFE_METHODS:
        return True

    return ACTION_PATH.match(path) is not None


def arrived_from_the_panel(headers: Headers) -> bool:
    """Whether the browser says this request started at the panel's own origin."""
    site = headers.get("sec-fetch-site")
    if site is not None:
        return site in OWN_ORIGIN_SITES

    origin = headers.get("origin")
    if origin is None:
        return True

    return urlsplit(origin).netloc.casefold() == (headers.get("host") or "").casefold()


class SameOriginOnly:
    """Answers ``403`` to a state-changing request from another origin."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        under_the_mount = scope["path"].removeprefix(scope.get("root_path", ""))
        if not changes_state(scope["method"], under_the_mount):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if arrived_from_the_panel(headers):
            await self.app(scope, receive, send)
            return

        origin = headers.get("origin") or headers.get("sec-fetch-site")
        logger.warning(f"admin panel refused a {scope['method']} {scope['path']} from {origin!r}")
        refusal = PlainTextResponse("This request did not come from the admin panel.", status_code=403)
        await refusal(scope, receive, send)
