"""Unit tests for the RBAC ORM models and permission configuration."""

from sqlalchemy import inspect

from src.modules.role.models import Role, RolePermission, UserRole
from src.modules.role.permissions import (
    PERMISSION_TREE,
    PermissionNames,
    is_known_permission,
)


def test_role_relationships_are_lazy_select():
    """RBAC relationships must not eagerly load related records."""
    assert inspect(Role).relationships["permissions"].lazy == "select"
    assert inspect(Role).relationships["user_roles"].lazy == "select"
    assert inspect(RolePermission).relationships["role"].lazy == "select"
    assert inspect(UserRole).relationships["user"].lazy == "select"
    assert inspect(UserRole).relationships["role"].lazy == "select"


def test_permission_tree_matches_permission_names():
    """Every permission in the tree must be a PermissionNames value."""
    permission_values = {
        value
        for name, value in vars(PermissionNames).items()
        if not name.startswith("_") and isinstance(value, str)
    }

    for parent in PERMISSION_TREE:
        assert parent.name in permission_values

        for child in parent.children:
            assert child.name in permission_values


def test_permission_tree_contains_expected_children():
    """Each permission parent must list exactly its defined child permissions."""
    expected_tree = {
        PermissionNames.user: {
            PermissionNames.user_read,
            PermissionNames.user_create,
            PermissionNames.user_update,
            PermissionNames.user_delete,
        },
        PermissionNames.role: {
            PermissionNames.role_read,
            PermissionNames.role_create,
            PermissionNames.role_update,
            PermissionNames.role_delete,
            PermissionNames.role_assign,
        },
        PermissionNames.tier: {
            PermissionNames.tier_read,
            PermissionNames.tier_create,
            PermissionNames.tier_update,
            PermissionNames.tier_delete,
        },
    }

    actual_tree = {
        parent.name: {child.name for child in parent.children}
        for parent in PERMISSION_TREE
    }

    assert actual_tree == expected_tree


def test_permission_name_validation():
    """Only permission names defined by PermissionNames are accepted."""
    assert is_known_permission(PermissionNames.user_read)
    assert is_known_permission(PermissionNames.role_assign)
    assert is_known_permission(PermissionNames.tier_delete)

    assert not is_known_permission("user.reed")
    assert not is_known_permission("unknown.permission")


def test_role_permission_and_user_role_can_be_created():
    """Role, RolePermission, and UserRole can be constructed together."""
    role = Role(
        name="test-role",
        description="Test role",
    )
    role.id = 1

    role_permission = RolePermission(
        role_id=role.id,
        permission_name=PermissionNames.user_read,
    )
    user_role = UserRole(
        user_id=1,
        role_id=role.id,
    )

    role.permissions.append(role_permission)
    role.user_roles.append(user_role)

    assert role.name == "test-role"
    assert role_permission.role_id == role.id
    assert role_permission.permission_name == PermissionNames.user_read
    assert user_role.role_id == role.id
