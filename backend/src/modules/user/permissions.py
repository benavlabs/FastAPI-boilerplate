"""User module permissions."""

from enum import StrEnum

from ..role.permission_registry import register_permissions


@register_permissions("user")
class UserPermission(StrEnum):
    """Permissions for user resources."""

    READ = "user.read"
    CREATE = "user.create"
    UPDATE = "user.update"
    DELETE = "user.delete"