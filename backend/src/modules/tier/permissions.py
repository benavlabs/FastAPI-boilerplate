"""Tier module permissions."""

from enum import StrEnum

from ..role.permission_registry import register_permissions


@register_permissions("tier")
class TierPermission(StrEnum):
    """Permissions for tier resources."""

    READ = "tier.read"
    CREATE = "tier.create"
    UPDATE = "tier.update"
    DELETE = "tier.delete"