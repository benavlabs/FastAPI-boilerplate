"""Authentication and role-based authorization dependencies."""

from typing import Annotated, Any, Collection

from crudauth import Principal
from crudauth.exceptions import ForbiddenException, UnauthorizedException
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...modules.role.models import RolePermission, UserRole
from ...modules.role.permission_registry import all_permissions
from ...modules.user.crud import crud_users
from ..database.session import async_session, local_session
from .setup import auth


PERMISSIONS_STATE_KEY = "rbac_permissions"


async def get_current_principal(
    principal: Annotated[Principal, Depends(auth.current_user())],
) -> Principal:
    """Return the authenticated crudauth principal."""

    return principal


async def get_optional_principal(
    principal: Annotated[Principal | None, Depends(auth.current_user(optional=True))],
) -> Principal | None:
    """Return the authenticated principal, or None when unauthenticated."""

    return principal


async def get_current_user(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: Annotated[AsyncSession, Depends(async_session)],
) -> dict[str, Any]:
    """Return the current authenticated user as a dictionary."""

    credentials_exception = UnauthorizedException("Not authenticated")

    if principal is None:
        raise credentials_exception

    user = await crud_users.get(db=db, id=principal.user_id, is_deleted=False)

    if user is None:
        raise credentials_exception

    return user


async def get_optional_user(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: Annotated[AsyncSession, Depends(async_session)],
) -> dict[str, Any] | None:
    """Return the current user, or None when unauthenticated."""

    if principal is None:
        return None

    return await crud_users.get(
        db=db,
        id=principal.user_id,
        is_deleted=False,
    )


async def get_current_superuser(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """Return the current user when they are a superuser."""

    if not current_user.get("is_superuser", False):
        raise ForbiddenException("Insufficient privileges")

    return current_user


async def load_permissions(
    principal: Principal,
    request: Request | None = None,
) -> frozenset[str]:
    """Load the effective registered permissions for a principal."""

    if request is not None:
        cached_permissions = getattr(
            request.state,
            PERMISSIONS_STATE_KEY,
            None,
        )
        if cached_permissions is not None:
            return cached_permissions

    if principal.is_superuser:
        permissions = frozenset(all_permissions())
    else:
        registered_permissions = all_permissions()

        if not registered_permissions:
            permissions = frozenset()
        else:
            statement = (
                select(RolePermission.permission_name)
                .join(
                    UserRole,
                    UserRole.role_id == RolePermission.role_id,
                )
                .where(
                    UserRole.user_id == principal.user_id,
                    RolePermission.permission_name.in_(registered_permissions),
                )
            )

            async with local_session() as db:
                result = await db.execute(statement)

            permissions = frozenset(result.scalars().all())

    if request is not None:
        setattr(
            request.state,
            PERMISSIONS_STATE_KEY,
            permissions,
        )

    return permissions


async def can_delegate_permissions(
    principal: Principal,
    permissions: Collection[str],
) -> bool:
    """Return whether a principal may delegate every specified permission."""

    needed = set(permissions)

    unknown_permissions = needed - all_permissions()

    if unknown_permissions:
        unknown = ", ".join(sorted(unknown_permissions))
        raise ValueError(f"Unknown permission name(s): {unknown}")

    if principal.is_superuser:
        return True

    effective_permissions = await load_permissions(principal)

    return needed <= effective_permissions


async def can_assign_role(
    principal: Principal,
    role_id: int,
) -> bool:
    """Return whether a principal may assign the specified role."""

    if principal.is_superuser:
        return True

    statement = select(RolePermission.permission_name).where(
        RolePermission.role_id == role_id,
    )

    async with local_session() as db:
        result = await db.execute(statement)

    role_permissions = set(result.scalars().all())

    if not role_permissions:
        return True

    registered_permissions = all_permissions()
    unknown_permissions = role_permissions - registered_permissions

    if unknown_permissions:
        return False

    effective_permissions = await load_permissions(principal)

    return role_permissions <= effective_permissions


def require_permissions(*needed: str):
    """Require all specified permissions for the authenticated principal."""

    unknown_permissions = set(needed) - all_permissions()

    if unknown_permissions:
        unknown = ", ".join(sorted(unknown_permissions))
        raise ValueError(f"Unknown permission name(s): {unknown}")

    async def check(principal: Principal) -> bool:
        if principal.is_superuser:
            return True

        permissions = await load_permissions(principal)

        return set(needed) <= permissions

    return Depends(auth.current_user(check=check))
