"""Middleware components for the FastAPI application."""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

# Two years, matching the HSTS preload-list requirement.
HSTS_MAX_AGE_SECONDS = 63072000

PUBLIC_CACHE_PREFIXES: tuple[str, ...] = ("/admin/statics/",)


class ClientCacheMiddleware(BaseHTTPMiddleware):
    """Set Cache-Control headers, withholding caching by default.

    Only the paths in ``public_prefixes`` are publicly cacheable. Everything else
    is ``private, no-store``: the admin panel, the docs and the health endpoint
    all answer with per-caller data or state, and a shared cache that kept one
    response could hand it to the next visitor. API paths keep the longer
    no-store wording they already had. A response that set its own
    ``Cache-Control`` is left alone, so a route can opt in to caching.

    Args:
        app: The ASGI app to wrap.
        max_age: Seconds a public response may be cached for.
        public_prefixes: Path prefixes whose bytes are the same for every caller, so a
            shared cache may keep them. The default is where SQLAdmin serves its own CSS
            and JS, under the panel's mount point; pass your own to add an application's
            static mount.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_age: int = 60,
        public_prefixes: tuple[str, ...] = PUBLIC_CACHE_PREFIXES,
    ) -> None:
        super().__init__(app)
        self.max_age: int = max_age
        self.public_prefixes: tuple[str, ...] = public_prefixes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response = await call_next(request)

        if "cache-control" in response.headers:
            return response

        path = request.url.path
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "private, no-cache, no-store, must-revalidate"
        elif path.startswith(self.public_prefixes):
            response.headers["Cache-Control"] = f"public, max-age={self.max_age}"
        else:
            response.headers["Cache-Control"] = "private, no-store"

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Set standard security headers on every response.

    Adds X-Content-Type-Options, X-Frame-Options, Referrer-Policy,
    Permissions-Policy, and HSTS (production/staging only).
    """

    def __init__(self, app: ASGIApp, environment: str = "development") -> None:
        super().__init__(app)
        self.environment = environment

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        if self.environment in ("production", "staging"):
            response.headers["Strict-Transport-Security"] = f"max-age={HSTS_MAX_AGE_SECONDS}; includeSubDomains"

        return response
