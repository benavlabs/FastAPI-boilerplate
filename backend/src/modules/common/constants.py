"""Common constants used across the application."""

from collections.abc import Callable

from ...infrastructure.http_exceptions import (
    DuplicateValueException,
    ForbiddenException,
    HTTPException,
    NotFoundException,
    RateLimitException,
    UnprocessableEntityException,
)
from .exceptions import (
    DomainError,
    InsufficientCreditsError,
    PermissionDeniedError,
    PersistenceError,
    ResourceExistsError,
    ResourceNotFoundError,
    UsageLimitExceededError,
    ValidationError,
)

# Generic error message for client-facing responses (never leak internal details)
GENERIC_ERROR_MESSAGE = "Something went wrong. Please try again."
SUPPORT_ID_LENGTH = 8

# Safety limits for queries that could be unbounded
MAX_ENTITLEMENTS_PER_USER = 100
DEFAULT_BATCH_SIZE = 100

EXCEPTION_MAPPING: dict[type[DomainError], Callable[[str], HTTPException]] = {
    InsufficientCreditsError: lambda message: HTTPException(status_code=402, detail=message or "Insufficient credits."),
    ResourceNotFoundError: lambda message: NotFoundException(detail="The requested resource was not found."),
    ResourceExistsError: lambda message: DuplicateValueException(detail="This resource already exists."),
    UsageLimitExceededError: lambda message: RateLimitException(detail="Usage limit exceeded."),
    ValidationError: lambda message: UnprocessableEntityException(detail="The request could not be processed."),
    PermissionDeniedError: lambda message: ForbiddenException(detail="You don't have permission for this action."),
    PersistenceError: lambda message: HTTPException(status_code=500, detail=GENERIC_ERROR_MESSAGE),
}
