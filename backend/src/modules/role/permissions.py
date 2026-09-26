"""Role module permissions."""

from enum import StrEnum

from .permission_registry import register_permissions


@register_permissions("role")
class RolePermission(StrEnum):
    """Permissions for role resources."""

    READ = "role.read"
    CREATE = "role.create"
    UPDATE = "role.update"
    DELETE = "role.delete"
    ASSIGN = "role.assign"