"""Role module for role-based access control."""

from .constants import ROLE_NAME_MAX_LENGTH
from .models import Role, RolePermission, UserRole
from .permissions import RolePermissionName

__all__ = [
    # Models
    "Role",
    "RolePermission",
    "UserRole",
    # Permissions
    "RolePermissionName",
    # Limits
    "ROLE_NAME_MAX_LENGTH",
]
