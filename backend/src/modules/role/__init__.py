"""Role module for role-based access control."""

from .models import Role, RolePermission, UserRole
from .permissions import RolePermission as RolePermissionName
from .permission_registry import (
    all_permissions,
    is_known_permission,
    permission_groups,
    register_permissions,
)

__all__ = [
    # Models
    "Role",
    "RolePermission",
    "UserRole",
    # Permissions
    "RolePermissionName",
    # Registry
    "all_permissions",
    "is_known_permission",
    "permission_groups",
    "register_permissions",
]