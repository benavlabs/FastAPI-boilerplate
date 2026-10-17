"""Unit tests for the RBAC ORM models and permission configuration."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.permissions import all_permissions, is_known_permission
from src.modules.role.models import Role, RolePermission, UserRole
from src.modules.user.models import User


def test_registered_permissions_are_known():
    """Registered flat permission names are recognized."""
    permissions = all_permissions()

    assert {"role.read", "role.assign"} <= permissions

    assert is_known_permission("role.read")
    assert is_known_permission("role.assign")


def test_unknown_permissions_are_not_known():
    """Unknown permission names are rejected by the registry."""
    assert not is_known_permission("user.reed")
    assert not is_known_permission("unknown.permission")
    assert not is_known_permission("user")


def test_role_permission_rejects_unknown_permission():
    """RolePermission must reject permission names outside the registry."""
    with pytest.raises(ValueError, match="Unknown permission name"):
        RolePermission(role_id=1, permission_name="user.reed")


def test_role_permission_accepts_registered_permission():
    """RolePermission accepts a registered flat permission name."""
    permission = RolePermission(role_id=1, permission_name="user.read")

    assert permission.role_id == 1
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
        select(func.count()).select_from(RolePermission).where(RolePermission.role_id == role_id)
    )
    user_role_count = await db_session.scalar(select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id))

    assert role_permission_count == 0
    assert user_role_count == 0


async def test_a_role_name_cannot_be_reused(db_session: AsyncSession):
    db_session.add(Role(name="duplicate"))
    await db_session.commit()
    db_session.add(Role(name="duplicate"))

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


async def test_a_role_cannot_carry_the_same_permission_twice(db_session: AsyncSession):
    role = Role(name="carrier")
    db_session.add(role)
    await db_session.flush()
    db_session.add(RolePermission(role_id=role.id, permission_name="user.read"))
    await db_session.commit()
    db_session.add(RolePermission(role_id=role.id, permission_name="user.read"))

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


async def test_a_user_cannot_be_assigned_the_same_role_twice(db_session: AsyncSession, test_user: dict):
    role = Role(name="assignee")
    db_session.add(role)
    await db_session.flush()
    db_session.add(UserRole(user_id=test_user["id"], role_id=role.id))
    await db_session.commit()
    db_session.add(UserRole(user_id=test_user["id"], role_id=role.id))

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


async def test_a_role_assignment_needs_a_user_that_exists(db_session: AsyncSession):
    role = Role(name="orphan")
    db_session.add(role)
    await db_session.flush()
    db_session.add(UserRole(user_id=999999, role_id=role.id))

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


async def test_deleting_a_user_removes_their_role_assignments(db_session: AsyncSession, test_user: dict):
    role = Role(name="departing")
    db_session.add(role)
    await db_session.flush()
    db_session.add(UserRole(user_id=test_user["id"], role_id=role.id))
    await db_session.commit()

    user = await db_session.get(User, test_user["id"])
    await db_session.delete(user)
    await db_session.commit()

    remaining = await db_session.scalar(select(func.count()).select_from(UserRole).where(UserRole.user_id == test_user["id"]))

    assert remaining == 0
