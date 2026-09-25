from __future__ import annotations

from dataclasses import dataclass, field


class PermissionNames:
    """Central list of permission name constants."""

    user = "user"
    user_read = f"{user}.read"
    user_create = f"{user}.create"
    user_update = f"{user}.update"
    user_delete = f"{user}.delete"

    role = "role"
    role_read = f"{role}.read"
    role_create = f"{role}.create"
    role_update = f"{role}.update"
    role_delete = f"{role}.delete"
    role_assign = f"{role}.assign"

    tier = "tier"
    tier_read = f"{tier}.read"
    tier_create = f"{tier}.create"
    tier_update = f"{tier}.update"
    tier_delete = f"{tier}.delete"


@dataclass(frozen=True)
class PermissionNode:
    """One node in the permission tree."""

    name: str
    children: tuple[PermissionNode, ...] = field(default_factory=tuple)


PERMISSION_TREE: tuple[PermissionNode, ...] = (
    PermissionNode(
        name=PermissionNames.user,
        children=(
            PermissionNode(name=PermissionNames.user_read),
            PermissionNode(name=PermissionNames.user_create),
            PermissionNode(name=PermissionNames.user_update),
            PermissionNode(name=PermissionNames.user_delete),
        ),
    ),
    PermissionNode(
        name=PermissionNames.role,
        children=(
            PermissionNode(name=PermissionNames.role_read),
            PermissionNode(name=PermissionNames.role_create),
            PermissionNode(name=PermissionNames.role_update),
            PermissionNode(name=PermissionNames.role_delete),
            PermissionNode(name=PermissionNames.role_assign),
        ),
    ),
    PermissionNode(
        name=PermissionNames.tier,
        children=(
            PermissionNode(name=PermissionNames.tier_read),
            PermissionNode(name=PermissionNames.tier_create),
            PermissionNode(name=PermissionNames.tier_update),
            PermissionNode(name=PermissionNames.tier_delete),
        ),
    ),
)


def is_known_permission(permission_name: str) -> bool:
    """Return whether a permission name is defined by PermissionNames."""
    return permission_name in {
        value
        for name, value in vars(PermissionNames).items()
        if not name.startswith("_") and isinstance(value, str)
    }
