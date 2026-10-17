"""User errors."""

from ..common.exceptions import ResourceExistsError, ResourceNotFoundError


class UserNotFoundError(ResourceNotFoundError):
    """Raised when a user cannot be found."""

    public_detail = "User not found."


class UserExistsError(ResourceExistsError):
    """Raised when attempting to create a user with an existing email or username."""

    public_detail = "A user with this email or username already exists."
