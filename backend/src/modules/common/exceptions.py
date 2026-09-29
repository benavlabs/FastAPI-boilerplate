"""Domain exception classes for business logic errors.

The status code comes from the closest base class in ``EXCEPTION_MAPPING``; a
feature chooses the client-facing message by setting ``public_detail`` on its own
subclass, so the mapping never has to name a feature's errors.
"""

from typing import ClassVar


class DomainError(Exception):
    """Base class for all domain-specific errors."""

    public_detail: ClassVar[str | None] = None


class ResourceNotFoundError(DomainError):
    """Raised when a requested resource cannot be found."""

    pass


class ResourceExistsError(DomainError):
    """Raised when attempting to create a resource that already exists."""

    pass


class ValidationError(DomainError):
    """Raised when data validation fails."""

    pass


class PermissionDeniedError(DomainError):
    """Raised when a user attempts an action they don't have permission for."""

    pass


class InsufficientCreditsError(DomainError):
    """Raised when a user doesn't have enough credits for an operation."""

    pass


class UsageLimitExceededError(DomainError):
    """Raised when a user exceeds their usage limits."""

    pass


class PersistenceError(DomainError):
    """Raised when a write the caller is entitled to make doesn't come back from the database."""

    pass
