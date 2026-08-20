from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.dependencies import get_current_user
from ...infrastructure.database.session import async_session
from ..common.exceptions import PermissionDeniedError
from .permissions import flatten_permission_tree
from .service import RoleService


def get_role_service() -> RoleService:
    return RoleService()


RoleServiceDep = Annotated[RoleService, Depends(get_role_service)]


def require_permissions(*permission_names: str, require_all: bool = True) -> Callable[..., Any]:
    """FastAPI dependency factory that checks the caller's effective permissions."""

    async def _dependency(
        current_user: Annotated[dict[str, Any], Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(async_session)],
        role_service: RoleServiceDep,
    ) -> dict[str, Any]:
        if current_user.get("is_superuser", False):
            return current_user

        granted = await role_service.get_effective_permissions(current_user["id"], db)
        needed = set(permission_names)
        ok = needed.issubset(granted) if require_all else bool(needed & granted)
        if not ok:
            raise PermissionDeniedError("Missing required permission(s)")
        return current_user

    return _dependency


def user_effective_permissions(user: Any) -> set[str]:
    """Flatten permissions from a loaded User ORM instance (admin display)."""
    if getattr(user, "is_superuser", False):
        return set(flatten_permission_tree())

    names: set[str] = set()
    for user_role in getattr(user, "user_roles", []) or []:
        role = getattr(user_role, "role", None)
        if role is None:
            continue
        for assignment in getattr(role, "permissions", []) or []:
            names.add(assignment.permission_name)
    return names