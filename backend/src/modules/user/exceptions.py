"""User errors."""

from ..common.exceptions import ResourceExistsError, ResourceNotFoundError


class UserNotFoundError(ResourceNotFoundError):
    """Raised when a user cannot be found."""

    public_detail = "User not found."


class UserExistsError(ResourceExistsError):
    """Raised when attempting to create a user with an existing email or username."""

    public_detail = "A user with this email or username already exists."


class EmailAlreadyRegisteredError(UserExistsError):
    """Raised when a signup names an address that already has an account.

    Its own error because a signup answers it the way it answers a signup that worked: the
    address is the caller's to know only if they hold the account. Anything that lets this
    reach a client reads as the conflict it inherits from.
    """
