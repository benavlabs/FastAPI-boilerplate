"""Middleware components for the FastAPI application."""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

# Two years, matching the HSTS preload-list requirement.
HSTS_MAX_AGE_SECONDS = 63072000


class ClientCacheMiddleware(BaseHTTPMiddleware):
    """Set Cache-Control headers.

    API endpoints get no-cache (authenticated, dynamic data).
    Static assets get public caching with the configured max_age.
    """

    def __init__(self, app: ASGIApp, max_age: int = 60) -> None:
        super().__init__(app)
        self.max_age: int = max_age

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "private, no-cache, no-store, must-revalidate"
        else:
            response.headers["Cache-Control"] = f"public, max-age={self.max_age}"
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
