"""Role module permissions."""

from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("role")
class RolePermissionName(StrEnum):
    """Permissions for role resources."""

    READ = "role.read"
    CREATE = "role.create"
    UPDATE = "role.update"
    DELETE = "role.delete"
    ASSIGN = "role.assign"
