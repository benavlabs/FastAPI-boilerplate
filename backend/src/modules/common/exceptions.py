"""Domain exception classes for business logic errors."""


class DomainError(Exception):
    """Base class for all domain-specific errors."""

    pass


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


class UserNotFoundError(ResourceNotFoundError):
    """Raised when a user cannot be found."""

    pass


class UserExistsError(ResourceExistsError):
    """Raised when attempting to create a user with an existing email or username."""

    pass


class TierNotFoundError(ResourceNotFoundError):
    """Raised when a tier cannot be found."""

    pass


class RateLimitNotFoundError(ResourceNotFoundError):
    """Raised when a rate limit cannot be found."""

    pass


class InsufficientCreditsError(DomainError):
    """Raised when a user doesn't have enough credits for an operation."""

    pass


class UsageLimitExceededError(DomainError):
    """Raised when a user exceeds their usage limits."""

    pass

class RoleNotFoundError(ResourceNotFoundError):
    """Raised when a role or role assignment cannot be found."""

    pass    
