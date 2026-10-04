"""The escalation checks: nobody hands out a grant they don't hold."""

from crudauth import Principal
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.permissions import all_permissions
from src.modules.role.delegation import can_assign_role, can_delegate_permissions
from src.modules.role.models import Role, RolePermission, UserRole


async def _role_with(db: AsyncSession, name: str, *permissions: str) -> Role:
    role = Role(name=name)
    db.add(role)
    await db.flush()
    db.add_all([RolePermission(role_id=role.id, permission_name=p) for p in permissions])
    await db.commit()
    return role


async def test_a_principal_can_delegate_what_it_holds(db_session: AsyncSession, test_user: dict):
    role = await _role_with(db_session, "editor", "user.read", "user.update")
    db_session.add(UserRole(user_id=test_user["id"], role_id=role.id))
    await db_session.commit()
    principal = Principal(user_id=test_user["id"])

    assert await can_delegate_permissions(db_session, principal, ["user.read"])
    assert not await can_delegate_permissions(db_session, principal, ["user.read", "user.delete"])


async def test_a_superuser_can_delegate_anything_registered(db_session: AsyncSession):
    principal = Principal(user_id=1, is_superuser=True)

    assert await can_delegate_permissions(db_session, principal, sorted(all_permissions()))


async def test_an_unregistered_permission_is_never_delegable(db_session: AsyncSession):
    """A typo or a removed permission is refused rather than raising into the route."""
    superuser = Principal(user_id=1, is_superuser=True)

    assert not await can_delegate_permissions(db_session, superuser, ["user.reed"])


async def test_assigning_a_role_needs_every_permission_it_carries(db_session: AsyncSession, test_user: dict):
    held = await _role_with(db_session, "held", "user.read")
    stronger = await _role_with(db_session, "stronger", "user.read", "user.delete")
    weaker = await _role_with(db_session, "weaker", "user.read")
    db_session.add(UserRole(user_id=test_user["id"], role_id=held.id))
    await db_session.commit()
    principal = Principal(user_id=test_user["id"])

    assert await can_assign_role(db_session, principal, weaker.id)
    assert not await can_assign_role(db_session, principal, stronger.id)


async def test_a_role_carrying_nothing_is_assignable(db_session: AsyncSession, test_user: dict):
    empty = await _role_with(db_session, "empty")
    principal = Principal(user_id=test_user["id"])

    assert await can_assign_role(db_session, principal, empty.id)


async def test_a_superuser_can_assign_any_role(db_session: AsyncSession):
    strong = await _role_with(db_session, "strong", "user.delete")

    assert await can_assign_role(db_session, Principal(user_id=1, is_superuser=True), strong.id)
