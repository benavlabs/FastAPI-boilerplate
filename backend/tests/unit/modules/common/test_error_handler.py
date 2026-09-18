"""Tests for the error handler module."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.modules.common.constants import GENERIC_ERROR_MESSAGE
from src.modules.common.exceptions import (
    InsufficientCreditsError,
    RateLimitNotFoundError,
    ResourceNotFoundError,
    TierNotFoundError,
    UserExistsError,
    UserNotFoundError,
    ValidationError,
)
from src.modules.common.utils.error_handler import (
    _generate_support_id,
    handle_exception,
    map_exception,
    register_exception_handlers,
)


def test_generate_support_id_length():
    support_id = _generate_support_id()
    assert len(support_id) == 8


def test_generate_support_id_unique():
    ids = {_generate_support_id() for _ in range(100)}
    assert len(ids) == 100


def _create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with error handlers registered."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-found")
    async def raise_not_found():
        raise ResourceNotFoundError("User 123 not found")

    @app.get("/validation")
    async def raise_validation():
        raise ValidationError("name must be at least 2 chars")

    @app.get("/credits")
    async def raise_credits():
        raise InsufficientCreditsError("You need 50 more credits")

    @app.get("/unhandled")
    async def raise_unhandled():
        raise RuntimeError("unexpected internal failure")

    return app


@pytest.fixture
def test_app():
    return _create_test_app()


@pytest.mark.asyncio
async def test_domain_error_returns_generic_message(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/not-found")

    assert response.status_code == 404
    body = response.json()
    # Must NOT contain the raw exception message
    assert "User 123" not in body["detail"]
    assert body["detail"] == GENERIC_ERROR_MESSAGE
    assert "support_id" in body
    assert len(body["support_id"]) == 8


@pytest.mark.asyncio
async def test_insufficient_credits_preserves_message(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/credits")

    assert response.status_code == 402
    body = response.json()
    # InsufficientCreditsError SHOULD keep its message
    assert "50 more credits" in body["detail"]
    assert "support_id" in body


@pytest.mark.asyncio
async def test_unhandled_error_returns_generic_500(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/unhandled")

    assert response.status_code == 500
    body = response.json()
    assert "unexpected internal failure" not in body["detail"]
    assert body["detail"] == GENERIC_ERROR_MESSAGE
    assert "support_id" in body


def test_map_exception_not_found_uses_generic_detail():
    """map_exception must return a generic message, not the raw error string."""
    exc = ResourceNotFoundError("User 42 has secret internal ID xyz")
    http_exc = map_exception(exc)
    assert http_exc.status_code == 404
    assert "User 42" not in http_exc.detail
    assert "secret" not in http_exc.detail
    assert "not found" in http_exc.detail.lower()


def test_map_exception_insufficient_credits_preserves_detail():
    """InsufficientCreditsError must keep its message for frontend upgrade prompts."""
    exc = InsufficientCreditsError("You need 50 more credits")
    http_exc = map_exception(exc)
    assert http_exc.status_code == 402
    assert "50 more credits" in http_exc.detail


def test_map_exception_prefers_specific_subclass_mapping():
    """Subclasses of ResourceNotFoundError must use their own mapping, not the parent's."""
    assert map_exception(UserNotFoundError("nope")).detail == "User not found."
    assert map_exception(TierNotFoundError("nope")).detail == "The requested tier was not found."
    assert map_exception(RateLimitNotFoundError("nope")).detail == "Rate limit configuration not found."
    # The base class itself still uses the generic not-found mapping
    assert map_exception(ResourceNotFoundError("nope")).detail == "The requested resource was not found."


def test_map_exception_user_exists_uses_specific_mapping():
    """UserExistsError must not fall through to the generic ResourceExistsError mapping."""
    http_exc = map_exception(UserExistsError(""))
    assert http_exc.status_code == 422
    assert http_exc.detail == "A user with this email or username already exists."


def test_handle_exception_returns_generic_for_domain_errors():
    """handle_exception (used by routes) must also return generic messages."""
    exc = ResourceNotFoundError("Payment record #123 not found in DB")
    http_exc = handle_exception(exc)
    assert http_exc is not None
    assert http_exc.status_code == 404
    assert "Payment record #123" not in http_exc.detail
