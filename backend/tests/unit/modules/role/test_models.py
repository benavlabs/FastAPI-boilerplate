"""Unit tests for the RBAC ORM models and permission configuration."""

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.role.models import Role, RolePermission, UserRole
from src.modules.role.permission_registry import all_permissions, is_known_permission
from src.modules.user.models import User


def test_role_relationships_are_lazy_select():
    """RBAC relationships must not eagerly load related records."""
    assert inspect(Role).relationships["permissions"].lazy == "select"
    assert inspect(Role).relationships["user_roles"].lazy == "select"
    assert inspect(RolePermission).relationships["role"].lazy == "select"
    assert inspect(UserRole).relationships["user"].lazy == "select"
    assert inspect(UserRole).relationships["role"].lazy == "select"
    assert inspect(User).relationships["user_roles"].lazy == "select"


def test_registered_permissions_are_known():
    """Registered flat permission names are recognized."""
    permissions = all_permissions()

    assert "user.read" in permissions
    assert "role.assign" in permissions
    assert "tier.delete" in permissions

    assert is_known_permission("user.read")
    assert is_known_permission("role.assign")
    assert is_known_permission("tier.delete")


def test_unknown_permissions_are_not_known():
    """Unknown permission names are rejected by the registry."""
    assert not is_known_permission("user.reed")
    assert not is_known_permission("unknown.permission")
    assert not is_known_permission("user")


def test_role_permission_rejects_unknown_permission():
    """RolePermission must reject permission names outside the registry."""
    with pytest.raises(ValueError, match="Unknown permission name"):
        RolePermission(
            permission_name="user.reed",
        )


def test_role_permission_accepts_registered_permission():
    """RolePermission accepts a registered flat permission name."""
    permission = RolePermission(
        permission_name="user.read",
    )

    assert permission.permission_name == "user.read"


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
        permission_name="user.read",
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