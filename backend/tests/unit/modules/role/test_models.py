"""Unit tests for the RBAC ORM models and permission configuration."""

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.role.models import Role, RolePermission, UserRole
from src.modules.role.permissions import (
    KNOWN_PERMISSIONS,
    PERMISSION_TREE,
    PermissionNames,
    is_known_permission,
)
from src.modules.user.models import User


def test_role_relationships_are_lazy_select():
    """RBAC relationships must not eagerly load related records."""
    assert inspect(Role).relationships["permissions"].lazy == "select"
    assert inspect(Role).relationships["user_roles"].lazy == "select"
    assert inspect(RolePermission).relationships["role"].lazy == "select"
    assert inspect(UserRole).relationships["user"].lazy == "select"
    assert inspect(UserRole).relationships["role"].lazy == "select"
    assert inspect(User).relationships["user_roles"].lazy == "select"


def test_permission_tree_matches_known_permissions():
    """Every known leaf permission must appear in the permission tree."""
    tree_values = {
        child.name
        for parent in PERMISSION_TREE
        for child in parent.children
    }

    assert tree_values == KNOWN_PERMISSIONS


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
    """Only known leaf permission names are accepted."""
    assert is_known_permission(PermissionNames.user_read)
    assert is_known_permission(PermissionNames.role_assign)
    assert is_known_permission(PermissionNames.tier_delete)

    assert not is_known_permission("user.reed")
    assert not is_known_permission("unknown.permission")
    assert not is_known_permission(PermissionNames.user)
    assert not is_known_permission(PermissionNames.role)
    assert not is_known_permission(PermissionNames.tier)


def test_role_permission_rejects_unknown_permission():
    """RolePermission must reject permission names outside the known leaves."""
    with pytest.raises(ValueError, match="Unknown permission name"):
        RolePermission(
            role_id=1,
            permission_name="user.reed",
        )


def test_role_permission_rejects_parent_permission():
    """RolePermission must reject permission-tree grouping nodes."""
    with pytest.raises(ValueError, match="Unknown permission name"):
        RolePermission(
            role_id=1,
            permission_name=PermissionNames.user,
        )


async def test_role_delete_cascades_to_permissions_and_user_roles(
    db_session: AsyncSession,
    test_user: dict,
):
    """Deleting a role must remove its permission and user-role assignments."""
    role = Role(
        name="test-role",
        description="Test role",
    )
    db_session.add(role)
    await db_session.flush()

    role_permission = RolePermission(
        role_id=role.id,
        permission_name=PermissionNames.user_read,
    )
    user_role = UserRole(
        user_id=test_user["id"],
        role_id=role.id,
    )

    db_session.add_all([role_permission, user_role])
    await db_session.commit()

    role_id = role.id

    await db_session.delete(role)
    await db_session.commit()

    role_permission_count = await db_session.scalar(
        select(func.count())
        .select_from(RolePermission)
        .where(RolePermission.role_id == role_id)
    )
    user_role_count = await db_session.scalar(
        select(func.count())
        .select_from(UserRole)
        .where(UserRole.role_id == role_id)
    )

    assert role_permission_count == 0
    assert user_role_count == 0
