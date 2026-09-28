"""Tests for middleware components."""

import pytest
from fastapi import FastAPI, Response
from httpx import ASGITransport, AsyncClient

from src.infrastructure.middleware import ClientCacheMiddleware, SecurityHeadersMiddleware


def _create_app_with_middleware(
    cache: bool = False,
    security: bool = False,
    environment: str = "development",
    max_age: int = 60,
) -> FastAPI:
    app = FastAPI()

    if cache:
        app.add_middleware(ClientCacheMiddleware, max_age=max_age)
    if security:
        app.add_middleware(SecurityHeadersMiddleware, environment=environment)

    @app.get("/api/v1/users")
    async def api_route():
        return {"users": []}

    @app.get("/static/logo.png")
    async def static_route():
        return {"file": "logo"}

    @app.get("/admin/statics/css/main.css")
    async def admin_static_route():
        return {"file": "css"}

    @app.get("/admin/user/list")
    async def admin_page_route():
        return {"page": "users"}

    @app.get("/health")
    async def health_route():
        return {"status": "ok"}

    @app.get("/downloads/report.csv")
    async def route_that_sets_its_own_header(response: Response):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return {"file": "report"}

    return app


# === ClientCacheMiddleware ===


@pytest.mark.asyncio
async def test_api_paths_get_no_cache():
    app = _create_app_with_middleware(cache=True, max_age=120)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/users")

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "private, no-cache, no-store, must-revalidate"


@pytest.mark.asyncio
async def test_admin_statics_get_public_cache():
    """The panel's own CSS and JS are the same bytes for everyone."""
    app = _create_app_with_middleware(cache=True, max_age=120)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/admin/statics/css/main.css")

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=120"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/admin/user/list", "/health", "/static/logo.png"])
async def test_everything_else_is_private_and_unstored(path: str):
    """An admin page holds another user's data; a shared cache must not serve it on."""
    app = _create_app_with_middleware(cache=True, max_age=120)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(path)

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_a_header_the_route_set_is_left_alone():
    """A route that knows its response is cacheable keeps saying so."""
    app = _create_app_with_middleware(cache=True, max_age=120)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/downloads/report.csv")

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"


# === SecurityHeadersMiddleware ===


@pytest.mark.asyncio
async def test_security_headers_present_in_dev():
    app = _create_app_with_middleware(security=True, environment="development")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/users")

    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["x-xss-protection"] == "0"
    assert "camera=()" in resp.headers["permissions-policy"]
    # HSTS should NOT be set in dev
    assert "strict-transport-security" not in resp.headers


@pytest.mark.asyncio
async def test_hsts_set_in_production():
    app = _create_app_with_middleware(security=True, environment="production")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/users")

    assert "strict-transport-security" in resp.headers
    assert "max-age=" in resp.headers["strict-transport-security"]
    assert "includeSubDomains" in resp.headers["strict-transport-security"]


@pytest.mark.asyncio
async def test_hsts_set_in_staging():
    app = _create_app_with_middleware(security=True, environment="staging")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/users")

    assert "strict-transport-security" in resp.headers
