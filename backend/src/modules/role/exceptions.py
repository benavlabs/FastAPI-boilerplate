"""Role errors."""

from ..common.exceptions import PermissionDeniedError, ResourceExistsError, ResourceNotFoundError


class RoleNotFoundError(ResourceNotFoundError):
    """Raised when a role cannot be found."""

    public_detail = "Role not found."


class RoleExistsError(ResourceExistsError):
    """Raised when a role name is already taken."""

    public_detail = "A role with this name already exists."


class PermissionDelegationError(PermissionDeniedError):
    """Raised when a caller would hand out a permission they don't hold themselves."""

    public_detail = "You can only grant permissions you hold yourself."


class RoleAssignmentError(PermissionDeniedError):
    """Raised when a caller would assign a role carrying a permission they don't hold."""

    public_detail = "You can only assign a role whose permissions you hold yourself."


class StrongerAccountError(PermissionDeniedError):
    """Raised when a caller would change the roles of an account stronger than their own."""

    public_detail = "You can only change the roles of an account that holds nothing you don't."
