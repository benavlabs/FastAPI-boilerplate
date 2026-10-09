"""Common constants used across the application."""

from collections.abc import Callable

from ...infrastructure.http_exceptions import (
    ConflictException,
    ForbiddenException,
    HTTPException,
    NotFoundException,
    UnprocessableEntityException,
)
from .exceptions import (
    DomainError,
    PermissionDeniedError,
    PersistenceError,
    ResourceExistsError,
    ResourceNotFoundError,
    ValidationError,
)

# Generic error message for client-facing responses (never leak internal details)
GENERIC_ERROR_MESSAGE = "Something went wrong. Please try again."
SUPPORT_ID_LENGTH = 8

DEFAULT_BATCH_SIZE = 100

EXCEPTION_MAPPING: dict[type[DomainError], Callable[[str], HTTPException]] = {
    ResourceNotFoundError: lambda message: NotFoundException(detail="The requested resource was not found."),
    ResourceExistsError: lambda message: ConflictException(detail="This resource already exists."),
    ValidationError: lambda message: UnprocessableEntityException(detail="The request could not be processed."),
    PermissionDeniedError: lambda message: ForbiddenException(detail="You don't have permission for this action."),
    PersistenceError: lambda message: HTTPException(status_code=500, detail=GENERIC_ERROR_MESSAGE),
}
