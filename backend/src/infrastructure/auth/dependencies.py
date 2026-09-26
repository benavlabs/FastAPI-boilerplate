"""Authentication and role-based authorization dependencies."""

from typing import Annotated, Any

from crudauth import Principal
from crudauth.exceptions import ForbiddenException, UnauthorizedException
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...modules.role.models import RolePermission, UserRole
from ...modules.role.permission_registry import all_permissions
from ...modules.user.crud import crud_users
from ..database.session import async_session, local_session
from .setup import auth


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

    return await crud_users.get(db=db, id=principal.user_id, is_deleted=False)


async def get_current_superuser(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """Return the current user when they are a superuser."""

    if not current_user.get("is_superuser", False):
        raise ForbiddenException("Insufficient privileges")

    return current_user


async def load_permissions(principal: Principal) -> frozenset[str]:
    """Load the effective registered permissions for a principal."""

    if principal.is_superuser:
        return frozenset(all_permissions())

    registered_permissions = all_permissions()
    if not registered_permissions:
        return frozenset()

    statement = (
        select(RolePermission.permission_name)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(
            UserRole.user_id == principal.user_id,
            RolePermission.permission_name.in_(registered_permissions),
        )
    )

    async with local_session() as db:
        result = await db.execute(statement)

    return frozenset(result.scalars().all())


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