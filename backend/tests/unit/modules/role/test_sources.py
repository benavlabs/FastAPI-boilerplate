"""The grants rbac contributes: the permissions a user's roles carry."""

from datetime import UTC, datetime

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.role.models import Role, RolePermission, UserRole
from src.modules.role.sources import role_permissions


async def _role_with(db: AsyncSession, name: str, *permissions: str) -> Role:
    role = Role(name=name)
    db.add(role)
    await db.flush()
    db.add_all([RolePermission(role_id=role.id, permission_name=p) for p in permissions])
    await db.commit()
    return role


async def test_the_source_reads_the_roles_assigned_to_the_user(db_session: AsyncSession, test_user: dict):
    role = await _role_with(db_session, "reader", "user.read", "tier.read")
    db_session.add(UserRole(user_id=test_user["id"], role_id=role.id))
    await db_session.commit()

    assert await role_permissions(db_session, test_user["id"]) == {"user.read", "tier.read"}


async def test_the_source_is_empty_without_a_role(db_session: AsyncSession, test_user: dict):
    assert await role_permissions(db_session, test_user["id"]) == frozenset()


async def test_the_source_ignores_a_stored_name_that_is_no_longer_registered(db_session: AsyncSession, test_user: dict):
    """A permission removed from the code must not keep granting anything."""
    role = await _role_with(db_session, "stale", "user.read")
    await db_session.execute(
        insert(RolePermission).values(
            role_id=role.id,
            permission_name="user.retired",
            created_at=datetime.now(UTC),
        )
    )
    db_session.add(UserRole(user_id=test_user["id"], role_id=role.id))
    await db_session.commit()

    assert await role_permissions(db_session, test_user["id"]) == {"user.read"}
