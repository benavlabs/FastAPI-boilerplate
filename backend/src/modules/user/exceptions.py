"""User errors."""

from ..common.exceptions import PermissionDeniedError, ResourceExistsError, ResourceNotFoundError


class UserNotFoundError(ResourceNotFoundError):
    """Raised when a user cannot be found."""

    public_detail = "User not found."


class UserExistsError(ResourceExistsError):
    """Raised when attempting to create a user with an existing email or username."""

    public_detail = "A user with this email or username already exists."


class EmailChangeNeedsPasswordError(PermissionDeniedError):
    """Raised when an email change arrives without the account's current password."""

    public_detail = "Confirm this change with your current password."


class ProviderAccountEmailChangeError(PermissionDeniedError):
    """Raised when an account that signs in with a provider tries to change its address."""

    public_detail = "This account signs in with a provider, so its address can't be changed here."
