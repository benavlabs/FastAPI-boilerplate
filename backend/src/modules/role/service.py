"""Reading and changing roles, and who holds them.

Every escalation check lives in ``delegation``: this service raises when one of them
refuses, and the routes answer 403 through the error mapping.
"""

from typing import Any, NoReturn

from crudauth import Principal
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..user.crud import crud_users
from ..user.exceptions import UserNotFoundError
from .delegation import can_assign_role, can_change_roles_of, can_delegate_permissions
from .exceptions import (
    PermissionDelegationError,
    RoleAssignmentError,
    RoleExistsError,
    RoleNotFoundError,
    StrongerAccountError,
)
from .models import Role, RolePermission, UserRole
from .schemas import RoleRead


class RoleService:
    """Roles, the permissions they carry, and the users they are assigned to."""

    async def get_all(self, db: AsyncSession, skip: int = 0, limit: int = 10) -> dict[str, Any]:
        """One page of roles, each with the permissions it carries."""
        total = await db.scalar(select(func.count()).select_from(Role))
        rows = (await db.execute(select(Role).order_by(Role.id).offset(skip).limit(limit))).scalars().all()
        carried = await self._permissions_of(db, [role.id for role in rows])

        return {
            "data": [RoleRead.of(role, carried.get(role.id, [])).model_dump() for role in rows],
            "total_count": total or 0,
        }

    async def get(self, role_id: int, db: AsyncSession) -> dict[str, Any]:
        """One role, with the permissions it carries.

        Raises:
            RoleNotFoundError: No role has that id.
        """
        role = await self._role(role_id, db)
        carried = await self._permissions_of(db, [role_id])

        return RoleRead.of(role, carried.get(role_id, [])).model_dump()

    async def create(
        self,
        name: str,
        description: str | None,
        permissions: list[str],
        principal: Principal,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Create a role carrying ``permissions``.

        Raises:
            RoleExistsError: A role already holds that name.
            PermissionDelegationError: The caller doesn't hold one of the permissions.
        """
        if await self._name_taken(name, db):
            raise RoleExistsError(f"Role '{name}' already exists")

        if not await can_delegate_permissions(db, principal, permissions):
            raise PermissionDelegationError("The caller does not hold every permission this role would carry")

        role = Role(name=name, description=description)
        db.add(role)
        try:
            await db.flush()
            db.add_all([RolePermission(role_id=role.id, permission_name=carried) for carried in permissions])
            await db.commit()
        except IntegrityError as collision:
            await self._refuse_taken_name(db, name, collision)

        return await self.get(role.id, db)

    async def update(self, role_id: int, values: dict[str, Any], principal: Principal, db: AsyncSession) -> dict[str, Any]:
        """Change a role's name or description.

        Raises:
            RoleNotFoundError: No role has that id.
            RoleExistsError: Another role already holds the new name.
            PermissionDelegationError: The caller doesn't hold what the role carries.
        """
        role = await self._role(role_id, db)
        carried = (await self._permissions_of(db, [role_id])).get(role_id, [])

        if not await can_delegate_permissions(db, principal, carried):
            raise PermissionDelegationError("The caller does not hold every permission this role carries")

        name = values.get("name")
        if name is not None and name != role.name and await self._name_taken(name, db):
            raise RoleExistsError(f"Role '{name}' already exists")

        for field, value in values.items():
            setattr(role, field, value)
        try:
            await db.commit()
        except IntegrityError as collision:
            await self._refuse_taken_name(db, name or role.name, collision)

        return await self.get(role_id, db)

    async def set_permissions(
        self, role_id: int, permissions: list[str], principal: Principal, db: AsyncSession
    ) -> dict[str, Any]:
        """Replace what a role carries.

        Raises:
            RoleNotFoundError: No role has that id.
            PermissionDelegationError: The caller doesn't hold one of the permissions,
                or doesn't hold one the role already carries.
        """
        await self._role(role_id, db)
        carried = (await self._permissions_of(db, [role_id])).get(role_id, [])

        if not await can_delegate_permissions(db, principal, set(permissions) | set(carried)):
            raise PermissionDelegationError("The caller does not hold every permission this change touches")

        await db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        db.add_all([RolePermission(role_id=role_id, permission_name=name) for name in permissions])
        await db.commit()

        return await self.get(role_id, db)

    async def delete(self, role_id: int, principal: Principal, db: AsyncSession) -> None:
        """Delete a role, and with it every assignment of it.

        Raises:
            RoleNotFoundError: No role has that id.
            PermissionDelegationError: The caller doesn't hold what the role carries.
        """
        await self._role(role_id, db)
        carried = (await self._permissions_of(db, [role_id])).get(role_id, [])

        if not await can_delegate_permissions(db, principal, carried):
            raise PermissionDelegationError("The caller does not hold every permission this role carries")

        await db.execute(delete(Role).where(Role.id == role_id))
        await db.commit()

    async def assign(self, role_id: int, user_id: int, principal: Principal, db: AsyncSession) -> None:
        """Give a user a role.

        Raises:
            RoleNotFoundError: No role has that id.
            UserNotFoundError: No account has that id.
            RoleAssignmentError: The caller doesn't hold what the role carries.
            StrongerAccountError: The account holds something the caller doesn't.
        """
        await self._assignable(role_id, user_id, principal, db)

        if not await db.scalar(select(UserRole.user_id).where(UserRole.user_id == user_id, UserRole.role_id == role_id)):
            db.add(UserRole(user_id=user_id, role_id=role_id))
            await db.commit()

    async def unassign(self, role_id: int, user_id: int, principal: Principal, db: AsyncSession) -> None:
        """Take a role away from a user.

        Raises:
            RoleNotFoundError: No role has that id.
            UserNotFoundError: No account has that id.
            RoleAssignmentError: The caller doesn't hold what the role carries.
            StrongerAccountError: The account holds something the caller doesn't.
        """
        await self._assignable(role_id, user_id, principal, db)

        await db.execute(delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id))
        await db.commit()

    async def roles_of(self, user_id: int, db: AsyncSession) -> list[dict[str, Any]]:
        """The roles a user holds, each with the permissions it carries.

        Raises:
            UserNotFoundError: No account has that id.
        """
        if not await crud_users.exists(db=db, id=user_id, is_deleted=False):
            raise UserNotFoundError(f"User with ID {user_id} not found")

        statement = select(Role).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
        held = (await db.execute(statement.order_by(Role.id))).scalars().all()
        carried = await self._permissions_of(db, [role.id for role in held])

        return [RoleRead.of(role, carried.get(role.id, [])).model_dump() for role in held]

    async def _assignable(self, role_id: int, user_id: int, principal: Principal, db: AsyncSession) -> None:
        """Raise unless the role and the account exist, and the caller may reach both."""
        await self._role(role_id, db)

        if not await crud_users.exists(db=db, id=user_id, is_deleted=False):
            raise UserNotFoundError(f"User with ID {user_id} not found")

        if not await can_assign_role(db, principal, role_id):
            raise RoleAssignmentError("The caller does not hold every permission this role carries")

        if not await can_change_roles_of(db, principal, user_id):
            raise StrongerAccountError("The account holds something the caller does not")

    @staticmethod
    async def _name_taken(name: str, db: AsyncSession) -> bool:
        """Whether a role already holds this name."""
        return await db.scalar(select(Role.id).where(Role.name == name)) is not None

    @staticmethod
    async def _refuse_taken_name(db: AsyncSession, name: str, collision: IntegrityError) -> NoReturn:
        """Undo the write and answer a name another request took first as a conflict.

        Raises:
            RoleExistsError: Always; the unique constraint refused the name.
        """
        await db.rollback()

        raise RoleExistsError(f"Role '{name}' already exists") from collision

    @staticmethod
    async def _role(role_id: int, db: AsyncSession) -> Role:
        """The role row.

        Raises:
            RoleNotFoundError: No role has that id.
        """
        role = await db.get(Role, role_id)
        if role is None:
            raise RoleNotFoundError(f"Role with ID {role_id} not found")

        return role

    @staticmethod
    async def _permissions_of(db: AsyncSession, role_ids: list[int]) -> dict[int, list[str]]:
        """The permission names each of these roles carries."""
        if not role_ids:
            return {}

        statement = select(RolePermission.role_id, RolePermission.permission_name).where(RolePermission.role_id.in_(role_ids))
        carried: dict[int, list[str]] = {}
        for role_id, permission_name in await db.execute(statement):
            carried.setdefault(role_id, []).append(permission_name)

        return carried
