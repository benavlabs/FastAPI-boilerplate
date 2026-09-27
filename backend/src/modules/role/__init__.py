"""Role module for role-based access control."""

from .constants import PERMISSION_NAME_MAX_LENGTH, ROLE_NAME_MAX_LENGTH
from .models import Role, RolePermission, UserRole
from .permission_registry import (
    all_permissions,
    discover_permissions,
    is_known_permission,
    permission_groups,
    register_permissions,
)
from .permissions import RolePermissionName

__all__ = [
    # Models
    "Role",
    "RolePermission",
    "UserRole",
    # Permissions
    "RolePermissionName",
    # Registry
    "all_permissions",
    "discover_permissions",
    "is_known_permission",
    "permission_groups",
    "register_permissions",
    # Limits
    "PERMISSION_NAME_MAX_LENGTH",
    "ROLE_NAME_MAX_LENGTH",
]
