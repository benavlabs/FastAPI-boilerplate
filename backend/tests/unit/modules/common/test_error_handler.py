"""Tests for the error handler module."""

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from src.modules.common.constants import GENERIC_ERROR_MESSAGE
from src.modules.common.exceptions import (
    PersistenceError,
    ResourceExistsError,
    ResourceNotFoundError,
    ValidationError,
)
from src.modules.common.utils.error_handler import (
    _generate_support_id,
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

    @app.get("/unhandled")
    async def raise_unhandled():
        raise RuntimeError("unexpected internal failure")

    return app


@pytest.fixture
def test_app():
    return _create_test_app()


@pytest.mark.asyncio
async def test_domain_error_answers_with_the_mapped_message(test_app):
    """The client is told what failed, from the mapping, never the raw message."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/not-found")

    assert response.status_code == 404
    body = response.json()
    assert "User 123" not in body["detail"]
    assert body["detail"] == "The requested resource was not found."
    assert "support_id" in body
    assert len(body["support_id"]) == 8


@pytest.mark.asyncio
async def test_validation_error_does_not_leak_its_message(test_app):
    """A domain ValidationError names the rule it broke in the log, not in the body."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/validation")

    assert response.status_code == 422
    body = response.json()
    assert "at least 2 chars" not in body["detail"]
    assert body["detail"] == "The request could not be processed."


@pytest.mark.asyncio
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


class _MissingWidget(ResourceNotFoundError):
    """A feature's own error, with the message it wants the client to see."""

    public_detail = "The requested widget was not found."


class _DuplicateWidget(ResourceExistsError):
    public_detail = "That widget already exists."


def test_a_features_own_message_replaces_the_base_one():
    """The status comes from the base class; the message from the error itself."""
    http_exc = map_exception(_MissingWidget("no such widget 7"))

    assert http_exc.status_code == map_exception(ResourceNotFoundError("x")).status_code
    assert http_exc.detail == "The requested widget was not found."


def test_a_base_error_keeps_the_generic_message():
    """An error that sets no message of its own must not leak the raised text."""
    assert map_exception(ResourceNotFoundError("user 7 is missing")).detail == "The requested resource was not found."


def test_the_status_still_comes_from_the_closest_base():
    http_exc = map_exception(_DuplicateWidget(""))

    assert http_exc.status_code == map_exception(ResourceExistsError("")).status_code
    assert http_exc.detail == "That widget already exists."


def test_a_resource_that_already_exists_is_a_conflict():
    assert map_exception(ResourceExistsError("tier 'free' already exists")).status_code == 409


def test_map_exception_persistence_failure_is_a_500():
    """A write that didn't come back is a server fault, not a duplicate."""
    http_exc = map_exception(PersistenceError("User row was not returned after insert"))

    assert http_exc.status_code == 500
    assert http_exc.detail == GENERIC_ERROR_MESSAGE
    assert "row was not returned" not in http_exc.detail


async def test_a_validation_failure_does_not_log_what_was_submitted(caplog):
    """pydantic hands a missing-field error the whole body, password included."""
    app = FastAPI()
    register_exception_handlers(app)

    class SignUp(BaseModel):
        username: str
        password: str

    @app.post("/signup")
    async def signup(body: SignUp) -> dict[str, str]:
        return {"status": "created"}

    with caplog.at_level(logging.WARNING):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/signup", json={"password": "hunter2-secret"})

    assert response.status_code == 422
    assert "hunter2-secret" not in caplog.text
    assert "username" in caplog.text
    assert "missing" in caplog.text


async def test_the_catch_all_message_does_not_repeat_the_exception(caplog):
    """The message carries the support id, method and path; the exception goes to the traceback."""
    app = _create_test_app()

    with caplog.at_level(logging.ERROR):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/unhandled")

    unhandled = [record for record in caplog.records if "Unhandled error" in record.getMessage()]

    assert response.status_code == 500
    assert unhandled
    assert all("GET /unhandled" in record.getMessage() for record in unhandled)
    assert all("unexpected internal failure" not in record.getMessage() for record in unhandled)
