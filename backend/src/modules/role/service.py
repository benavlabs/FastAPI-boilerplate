from typing import Any

from fastcrud.types import GetMultiResponseDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import PermissionDeniedError, ResourceExistsError, RoleNotFoundError, ValidationError
from .crud import crud_role_permissions, crud_roles, crud_user_roles
from .permissions import flatten_permission_tree, is_known_permission
from .schemas import (
    RoleCreate,
    RoleCreateInternal,
    RolePermissionCreate,
    RoleRead,
    RoleUpdate,
    UserRoleCreate,
)


class RoleService:
    """Business logic for roles, permission assignment, and user-role mapping."""

    async def create(self, role: RoleCreate, db: AsyncSession) -> dict[str, Any]:
        """Create a new role."""
        role_dict = role.model_dump()
        if await crud_roles.exists(db=db, name=role_dict["name"]):
            raise ResourceExistsError(f"Role with name '{role_dict['name']}' already exists")

        created = await crud_roles.create(db=db, object=RoleCreateInternal(**role_dict), schema_to_select=RoleRead)
        if not created:
            raise ResourceExistsError("Failed to create role")
        return created

    async def get_all(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> GetMultiResponseDict:
        """Paginated list of non-deleted roles."""
        return await crud_roles.get_multi(db=db, offset=skip, limit=limit, schema_to_select=RoleRead, is_deleted=False)

    async def get_by_id(self, role_id: int, db: AsyncSession) -> dict[str, Any]:
        """Retrieve a role by ID."""
        role = await crud_roles.get(db=db, id=role_id, schema_to_select=RoleRead, is_deleted=False)
        if not role:
            raise RoleNotFoundError(f"Role with ID {role_id} not found")
        role["permissions"] = await self.list_permission_names(role_id, db)
        return role

    async def get_by_name(self, name: str, db: AsyncSession) -> dict[str, Any]:
        """Retrieve a role by name."""
        role = await crud_roles.get(db=db, name=name, schema_to_select=RoleRead, is_deleted=False)
        if not role:
            raise RoleNotFoundError(f"Role with name '{name}' not found")
        role["permissions"] = await self.list_permission_names(role["id"], db)
        return role

    async def update(self, role_id: int, role_update: RoleUpdate, db: AsyncSession) -> None:
        """Update a role by ID."""
        existing = await crud_roles.get(db=db, id=role_id, schema_to_select=RoleRead)
        if not existing:
            raise RoleNotFoundError(f"Role with ID {role_id} not found")

        update_data = role_update.model_dump(exclude_unset=True)
        if "name" in update_data and update_data["name"] != existing["name"]:
            if await crud_roles.exists(db=db, name=update_data["name"]):
                raise ResourceExistsError(f"Role with name '{update_data['name']}' already exists")

        await crud_roles.update(db=db, object=role_update, id=role_id)

    async def soft_delete(self, role_id: int, db: AsyncSession) -> None:
        """Soft-delete a role."""
        existing = await crud_roles.get(db=db, id=role_id, schema_to_select=RoleRead, is_deleted=False)
        if not existing:
            raise RoleNotFoundError(f"Role with ID {role_id} not found")
        await crud_roles.delete(db=db, id=role_id)

    async def list_permission_names(self, role_id: int, db: AsyncSession) -> list[str]:
        """Return permission names assigned to a role."""
        rows = await crud_role_permissions.get_multi(db=db, role_id=role_id, limit=1000)
        data = rows.get("data", []) if isinstance(rows, dict) else rows
        return [row["permission_name"] for row in data]

    async def assign_permission(self, payload: RolePermissionCreate, db: AsyncSession) -> dict[str, Any]:
        """Attach a known permission name to a role."""
        await self.get_by_id(payload.role_id, db)
        if not is_known_permission(payload.permission_name):
            raise ValidationError(f"Unknown permission '{payload.permission_name}'")
        if await crud_role_permissions.exists(db=db, role_id=payload.role_id, permission_name=payload.permission_name):
            raise ResourceExistsError("Permission already assigned to this role")
        created = await crud_role_permissions.create(db=db, object=payload)
        if not created:
            raise ResourceExistsError("Failed to assign permission")
        return created

    async def remove_permission(self, role_id: int, permission_name: str, db: AsyncSession) -> None:
        """Remove a permission from a role."""
        existing = await crud_role_permissions.get(db=db, role_id=role_id, permission_name=permission_name)
        if not existing:
            raise RoleNotFoundError("Role permission assignment not found")
        await crud_role_permissions.db_delete(db=db, id=existing["id"])

    async def assign_role(self, payload: UserRoleCreate, db: AsyncSession) -> dict[str, Any]:
        """Assign a role to a user."""
        await self.get_by_id(payload.role_id, db)
        if await crud_user_roles.exists(db=db, user_id=payload.user_id, role_id=payload.role_id):
            raise ResourceExistsError("User already has this role")
        created = await crud_user_roles.create(db=db, object=payload)
        if not created:
            raise ResourceExistsError("Failed to assign role")
        return created

    async def remove_role(self, user_id: int, role_id: int, db: AsyncSession) -> None:
        """Remove a role from a user."""
        existing = await crud_user_roles.get(db=db, user_id=user_id, role_id=role_id)
        if not existing:
            raise RoleNotFoundError("User role assignment not found")
        await crud_user_roles.db_delete(db=db, id=existing["id"])

    async def get_user_role_ids(self, user_id: int, db: AsyncSession) -> list[int]:
        """Return role IDs assigned to a user."""
        rows = await crud_user_roles.get_multi(db=db, user_id=user_id, limit=1000)
        data = rows.get("data", []) if isinstance(rows, dict) else rows
        return [row["role_id"] for row in data]

    async def get_effective_permissions(self, user_id: int, db: AsyncSession) -> set[str]:
        """Union of permission names from all of a user's roles."""
        from .models import RolePermission, UserRole

        stmt = (
            select(RolePermission.permission_name)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
        )
        result = await db.execute(stmt)
        return set(result.scalars().all())

    def all_permission_names(self) -> list[str]:
        """All known permission names from the tree."""
        return flatten_permission_tree()

    def verify_superuser(self, user: dict[str, Any], action: str = "manage roles") -> None:
        """Require superuser for privileged role management."""
        if not user.get("is_superuser", False):
            raise PermissionDeniedError(f"Only superusers can {action}")