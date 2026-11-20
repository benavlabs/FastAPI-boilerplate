"""Utility functions for mapping domain exceptions to HTTP exceptions."""

import uuid as uuid_mod
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ....infrastructure.http_exceptions import (
    HTTPException,
)
from ....infrastructure.logging import get_logger
from ..constants import EXCEPTION_MAPPING, GENERIC_ERROR_MESSAGE, INVALID_REQUEST_MESSAGE, SUPPORT_ID_LENGTH
from ..exceptions import DomainError

logger = get_logger()


def generate_support_id() -> str:
    """Generate a short support ID for error tracking."""
    return str(uuid_mod.uuid4())[:SUPPORT_ID_LENGTH]


def where_and_why(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """Each validation failure's ``loc``, ``msg`` and ``type``, and nothing else.

    pydantic's ``input`` is the value that failed, and for a missing field it is the whole
    body; ``ctx`` can hold it too. Neither is something to answer with or log: a body
    carries passwords and tokens.
    """
    return [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in errors]


def invalid_request(support_id: str, errors: list[dict[str, Any]]) -> JSONResponse:
    """The ``422`` every refused request gets: the generic message, where and why, and a support id."""
    return JSONResponse(
        status_code=422,
        content={"detail": INVALID_REQUEST_MESSAGE, "errors": errors, "support_id": support_id},
    )


INVALID_REQUEST_SCHEMAS: dict[str, dict[str, Any]] = {
    "ValidationError": {
        "title": "ValidationError",
        "type": "object",
        "properties": {
            "loc": {"title": "Location", "type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]}},
            "msg": {"title": "Message", "type": "string"},
            "type": {"title": "Error Type", "type": "string"},
        },
        "required": ["loc", "msg", "type"],
    },
    "HTTPValidationError": {
        "title": "HTTPValidationError",
        "type": "object",
        "properties": {
            "detail": {"title": "Detail", "type": "string"},
            "errors": {"title": "Errors", "type": "array", "items": {"$ref": "#/components/schemas/ValidationError"}},
            "support_id": {"title": "Support Id", "type": "string"},
        },
        "required": ["detail"],
    },
}
"""What ``invalid_request`` answers, in place of the schemas FastAPI documents its own ``422`` with.

Only ``detail`` is required: a domain ``ValidationError`` and a refusal a route raises itself
answer ``422`` with a message of their own and no ``errors``."""


INVALID_REQUEST_RESPONSE: dict[str, Any] = {
    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPValidationError"}}}
}
"""The body a route that documents its own ``422`` points at, as FastAPI's own ``422`` does."""


def _document_the_invalid_request(app: FastAPI) -> None:
    """Have the OpenAPI document describe the ``422`` this app answers, not FastAPI's own."""
    build = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schemas = build().get("components", {}).get("schemas", {})
            schemas.update({name: schema for name, schema in INVALID_REQUEST_SCHEMAS.items() if name in schemas})

        return app.openapi_schema or build()

    app.openapi = openapi  # type: ignore[method-assign]


def map_exception(error: DomainError) -> HTTPException:
    """Map a domain exception to a corresponding HTTP exception.

    Walks the exception's MRO and uses the first exact-type match found in
    EXCEPTION_MAPPING, so the most specific mapping wins regardless of the
    order entries appear in the mapping. The status comes from that base class;
    the message comes from the error's own ``public_detail`` when it sets one.
    """
    for exception_class in type(error).__mro__:
        mapper = EXCEPTION_MAPPING.get(exception_class)
        if mapper is not None:
            http_exception = mapper(str(error))
            if error.public_detail is not None:
                http_exception.detail = error.public_detail

            return http_exception

    logger.error(f"Unmapped domain error: {type(error).__name__}: {error}")
    return HTTPException(status_code=500, detail=GENERIC_ERROR_MESSAGE)


class CatchAllErrorMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return generic 500 with support ID."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception:
            support_id = generate_support_id()
            logger.exception(f"Unhandled error [{support_id}] on {request.method} {request.url.path}")
            return JSONResponse(
                status_code=500,
                content={"detail": GENERIC_ERROR_MESSAGE, "support_id": support_id},
            )


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers for domain and validation exceptions.

    All handlers log full details server-side and answer the client with the
    message ``EXCEPTION_MAPPING`` defines for that failure plus a support_id -
    enough to say what went wrong, never the raw domain message, which can name
    rows the caller isn't entitled to know about.
    """
    app.add_middleware(CatchAllErrorMiddleware)
    _document_the_invalid_request(app)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Answer and log where and why a request failed to validate, never what it carried."""
        support_id = generate_support_id()
        failures = where_and_why(exc.errors())
        logger.warning(f"Validation error [{support_id}] on {request.method} {request.url.path}: {failures}")
        return invalid_request(support_id, failures)

    @app.exception_handler(DomainError)
    async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
        support_id = generate_support_id()
        http_exception = map_exception(exc)

        logger.warning(f"Domain error [{support_id}] on {request.method} {request.url.path}: {type(exc).__name__}: {exc}")
        return JSONResponse(
            status_code=http_exception.status_code,
            content={"detail": http_exception.detail, "support_id": support_id},
        )
