"""Utility functions for mapping domain exceptions to HTTP exceptions."""

import uuid as uuid_mod

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ....infrastructure.auth.http_exceptions import (
    HTTPException,
)
from ....infrastructure.logging import get_logger
from ..constants import EXCEPTION_MAPPING, GENERIC_ERROR_MESSAGE, SUPPORT_ID_LENGTH
from ..exceptions import (
    DomainError,
    InsufficientCreditsError,
)

logger = get_logger()


def _generate_support_id() -> str:
    """Generate a short support ID for error tracking."""
    return str(uuid_mod.uuid4())[:SUPPORT_ID_LENGTH]


def map_exception(error: DomainError) -> HTTPException:
    """Map a domain exception to a corresponding HTTP exception.

    Walks the exception's MRO and uses the first exact-type match found in
    EXCEPTION_MAPPING, so the most specific mapping wins regardless of the
    order entries appear in the mapping.
    """
    for exception_class in type(error).__mro__:
        mapper = EXCEPTION_MAPPING.get(exception_class)
        if mapper is not None:
            return mapper(str(error))

    logger.error(f"Unmapped domain error: {type(error).__name__}: {error}")
    return HTTPException(status_code=500, detail=GENERIC_ERROR_MESSAGE)


class CatchAllErrorMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return generic 500 with support ID."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            support_id = _generate_support_id()
            logger.exception(f"Unhandled error [{support_id}] on {request.method} {request.url.path}: {exc}")
            return JSONResponse(
                status_code=500,
                content={"detail": GENERIC_ERROR_MESSAGE, "support_id": support_id},
            )


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers for domain and validation exceptions.

    All handlers log full details server-side and return only a generic message
    + support_id to the client. Exception: InsufficientCreditsError (402) keeps
    its message since the frontend needs the credit info for upgrade prompts.
    """
    app.add_middleware(CatchAllErrorMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        support_id = _generate_support_id()
        logger.warning(f"Validation error [{support_id}] on {request.method} {request.url.path}: {exc.errors()}")
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid request. Please check your input and try again.", "support_id": support_id},
        )

    @app.exception_handler(DomainError)
    async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
        support_id = _generate_support_id()
        http_exception = map_exception(exc)

        if isinstance(exc, InsufficientCreditsError):
            logger.info(f"Insufficient credits [{support_id}] on {request.method} {request.url.path}: {exc}")
            return JSONResponse(
                status_code=http_exception.status_code,
                content={"detail": http_exception.detail, "support_id": support_id},
            )

        logger.warning(f"Domain error [{support_id}] on {request.method} {request.url.path}: {type(exc).__name__}: {exc}")
        return JSONResponse(
            status_code=http_exception.status_code,
            content={"detail": GENERIC_ERROR_MESSAGE, "support_id": support_id},
        )


def handle_exception(error: Exception) -> HTTPException | None:
    """Handle an exception and return an appropriate HTTP exception if possible.

    For use in route handlers when you want to handle exceptions manually.
    """
    if isinstance(error, DomainError):
        return map_exception(error)
    elif isinstance(error, HTTPException):
        return error
    return None
