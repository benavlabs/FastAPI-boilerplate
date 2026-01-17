"""
Exception Handler Middleware for FastAPI.

Catches all exceptions and returns consistent JSON responses using the APIResponse schema.
Handles:
- RequestValidationError (422): Pydantic/FastAPI validation errors
- HTTPException: Standard FastAPI HTTP exceptions
- CustomException: FastCRUD custom exceptions
- Generic Exception (500): Unexpected server errors
"""

import logging
import traceback

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from ..core.config import EnvironmentOption, settings
from ..schemas.api_response import APIResponse, ValidationErrorDetail

logger = logging.getLogger(__name__)


# User-friendly error message translations for Pydantic error types
ERROR_MESSAGES = {
    # Missing/Required errors
    "missing": "This field is required",
    "value_error.missing": "This field is required",
    # Type errors
    "type_error.none.not_allowed": "This field cannot be null",
    "type_error.integer": "Must be a valid integer",
    "type_error.float": "Must be a valid number",
    "type_error.bool": "Must be true or false",
    "type_error.str": "Must be a valid string",
    "type_error.list": "Must be a valid list",
    "type_error.dict": "Must be a valid object",
    # String validation
    "string_too_short": "This field is too short",
    "string_too_long": "This field is too long",
    "string_type": "Must be a valid string",
    "string_pattern_mismatch": "Invalid format",
    # Email validation
    "value_error.email": "Must be a valid email address",
    # Number validation
    "greater_than": "Value is too small",
    "greater_than_equal": "Value is too small",
    "less_than": "Value is too large",
    "less_than_equal": "Value is too large",
    # JSON errors
    "json_invalid": "Invalid JSON format",
    "json_type": "Expected valid JSON",
    # Extra fields
    "extra_forbidden": "Unknown field not allowed",
}


def get_friendly_message(error_type: str, original_msg: str, ctx: dict | None = None) -> str:
    """Convert Pydantic error type to user-friendly message.

    Parameters
    ----------
    error_type : str
        The Pydantic error type (e.g., "missing", "string_too_short")
    original_msg : str
        The original Pydantic error message
    ctx : dict | None
        Additional context from the error (e.g., min_length, max_length)

    Returns
    -------
    str
        User-friendly error message
    """
    # Check if we have a custom message for this error type
    if error_type in ERROR_MESSAGES:
        base_msg = ERROR_MESSAGES[error_type]

        # Add context if available
        if ctx:
            if error_type == "string_too_short" and "min_length" in ctx:
                return f"Must be at least {ctx['min_length']} characters"
            if error_type == "string_too_long" and "max_length" in ctx:
                return f"Must be at most {ctx['max_length']} characters"
            if error_type == "greater_than" and "gt" in ctx:
                return f"Must be greater than {ctx['gt']}"
            if error_type == "less_than" and "lt" in ctx:
                return f"Must be less than {ctx['lt']}"

        return base_msg

    # Return original message if no translation found
    return original_msg


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware to catch and handle all exceptions with consistent JSON responses.

    This middleware wraps all request handling and catches any exceptions that occur,
    converting them into standardized APIResponse JSON format.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.
    debug : bool, optional
        If True, includes stack traces in error responses. Defaults to False.

    Attributes
    ----------
    debug : bool
        Whether to include detailed error information in responses.
    """

    def __init__(self, app: FastAPI, debug: bool = False) -> None:
        super().__init__(app)
        self.debug = debug

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process the request and handle any exceptions.

        Parameters
        ----------
        request : Request
            The incoming HTTP request.
        call_next : RequestResponseEndpoint
            The next middleware or route handler.

        Returns
        -------
        Response
            Either the normal response or an error response in APIResponse format.
        """
        try:
            response = await call_next(request)
            return response

        except RequestValidationError as exc:
            return self._handle_validation_error(exc)

        except StarletteHTTPException as exc:
            return self._handle_http_exception(exc)

        except Exception as exc:
            return self._handle_generic_exception(exc, request)

    def _handle_validation_error(self, exc: RequestValidationError) -> JSONResponse:
        """Handle Pydantic/FastAPI validation errors."""
        errors = []
        for error in exc.errors():
            errors.append(
                ValidationErrorDetail(
                    loc=[str(loc) for loc in error.get("loc", [])],
                    msg=error.get("msg", "Validation error"),
                    type=error.get("type", "value_error"),
                )
            )

        logger.warning(f"Validation error: {errors}")

        response = APIResponse(
            data=[error.model_dump() for error in errors],
            isSuccess=False,
            message="Validation failed",
            statusCode=422,
        )

        return JSONResponse(
            status_code=422,
            content=response.model_dump(),
        )

    def _handle_http_exception(self, exc: StarletteHTTPException) -> JSONResponse:
        """Handle FastAPI/Starlette HTTP exceptions."""
        logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")

        response = APIResponse(
            data=None,
            isSuccess=False,
            message=str(exc.detail) if exc.detail else "An error occurred",
            statusCode=exc.status_code,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(),
        )

    def _handle_generic_exception(self, exc: Exception, request: Request) -> JSONResponse:
        """Handle unexpected exceptions."""
        # Log the full traceback for debugging
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}: {exc}",
            exc_info=True,
        )

        # Build error message based on debug mode
        message = "Internal server error"
        data = None

        if self.debug:
            message = str(exc)
            data = {
                "exception_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            }

        response = APIResponse(
            data=data,
            isSuccess=False,
            message=message,
            statusCode=500,
        )

        return JSONResponse(
            status_code=500,
            content=response.model_dump(),
        )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers directly on the FastAPI app.

    This is an alternative to the middleware approach, using FastAPI's
    built-in exception handler registration.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.
    """
    is_debug = settings.ENVIRONMENT != EnvironmentOption.PRODUCTION

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for error in exc.errors():
            error_type = error.get("type", "value_error")
            original_msg = error.get("msg", "Validation error")
            ctx = error.get("ctx")  # Contains min_length, max_length, etc.

            # Get user-friendly message
            friendly_msg = get_friendly_message(error_type, original_msg, ctx)

            # Get field name (last item in location, skip 'body')
            loc = error.get("loc", [])
            field_name = loc[-1] if loc else "field"

            errors.append(
                {
                    "field": str(field_name),
                    "message": friendly_msg,
                    "type": error_type,
                }
            )

        logger.warning(f"Validation error on {request.url.path}: {errors}")

        return JSONResponse(
            status_code=422,
            content=APIResponse(
                data=errors,
                isSuccess=False,
                message="Validation failed",
                statusCode=422,
            ).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        logger.warning(f"HTTP {exc.status_code} on {request.url.path}: {exc.detail}")

        return JSONResponse(
            status_code=exc.status_code,
            content=APIResponse(
                data=None,
                isSuccess=False,
                message=str(exc.detail) if exc.detail else "An error occurred",
                statusCode=exc.status_code,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}: {exc}",
            exc_info=True,
        )

        data = None
        message = "Internal server error"

        if is_debug:
            message = str(exc)
            data = {
                "exception_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            }

        return JSONResponse(
            status_code=500,
            content=APIResponse(
                data=data,
                isSuccess=False,
                message=message,
                statusCode=500,
            ).model_dump(),
        )
