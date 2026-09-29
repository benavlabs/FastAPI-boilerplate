"""Auth dependencies: resolve the crudauth ``Principal``, the dict-compat user, and permissions.

Routes depend on these; they wrap the crudauth ``auth`` singleton so the session
engine (validation, CSRF, lockout) lives in crudauth while handlers keep their
existing dict/Principal contracts. ``get_current_user`` returns the same user
dict the rest of the app (and the API-key module) already consumes, so the public
contract is unchanged.
"""

from collections.abc import Collection
from typing import Annotated, Any

from crudauth import Principal
from crudauth.exceptions import ForbiddenException, UnauthorizedException
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...modules.role.models import RolePermission, UserRole
from ...modules.user.crud import crud_users
from ..database.session import async_session
from ..permissions import all_permissions
from .setup import auth


async def get_current_principal(
    principal: Annotated[Principal, Depends(auth.current_user())],
) -> Principal:
    """The authenticated crudauth ``Principal`` (session-validated, CSRF-enforced).

    A single named dependency so routes that need the session id
    (``principal.metadata["session_id"]``) or the transport can depend on it and
    tests can override it. Raises 401 when there is no valid session.
    """
    return principal


async def get_optional_principal(
    principal: Annotated[Principal | None, Depends(auth.current_user(optional=True))],
) -> Principal | None:
    """The crudauth ``Principal`` if authenticated, else ``None`` (never raises on absence).

    Still enforces CSRF on unsafe methods when a session is present.
    """
    return principal


async def get_current_user(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: Annotated[AsyncSession, Depends(async_session)],
) -> dict[str, Any]:
    """Get the current authenticated user as a dict (resolved by crudauth).

    crudauth validates the cookie and enforces CSRF on unsafe methods; we re-load
    the full row (filtering soft-deleted users) so the return value stays the dict
    the handlers expect.

    Raises:
        UnauthorizedException: If not authenticated or the user doesn't exist.
    """
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
    """Get the current user as a dict if authenticated, None otherwise."""
    if principal is None:
        return None

    return await crud_users.get(db=db, id=principal.user_id, is_deleted=False)


async def get_current_superuser(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """Get the current user as a dict, requiring superuser privileges (403 otherwise)."""
    if not current_user.get("is_superuser", False):
        raise ForbiddenException("Insufficient privileges")

    return current_user


async def load_permissions(db: AsyncSession, user_id: int, *, is_superuser: bool = False) -> frozenset[str]:
    """The permissions a user effectively holds, through the roles assigned to them.

    Reads through the session the request already uses, so it sees the same data
    (and the same database under test overrides) as the route it authorizes.
    Stored names that are no longer registered are ignored, so removing a
    permission from the code can't grant anything.

    Args:
        db: Database session for the lookup.
        user_id: The user whose roles to read.
        is_superuser: When true, every registered permission is granted without a query.

    Returns:
        The registered permission names the user holds.
    """
    registered = all_permissions()

    if is_superuser:
        return registered

    if not registered:
        return frozenset()

    statement = (
        select(RolePermission.permission_name)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(
            UserRole.user_id == user_id,
            RolePermission.permission_name.in_(registered),
        )
    )
    result = await db.execute(statement)

    return frozenset(result.scalars().all())


async def get_current_permissions(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(async_session)],
) -> frozenset[str]:
    """The current user's effective permissions, resolved once per request.

    FastAPI caches a dependency's result for the length of a request, so however
    many ``require_permissions`` guards and route parameters ask for permissions,
    the join runs once.
    """
    return await load_permissions(db, principal.user_id, is_superuser=principal.is_superuser)


def require_permissions(*needed: str) -> Any:
    """A dependency that answers 403 unless the caller holds every named permission.

    Superusers pass without a lookup. Unknown names are a programming error and
    raise at import time, when the route is declared, rather than at request time.

    Example:
        ```python
        @router.get("/", dependencies=[require_permissions("user.read")])
        async def get_users(...): ...
        ```
    """
    required = frozenset(needed)
    unknown = required - all_permissions()

    if unknown:
        raise ValueError(f"Unknown permission name(s): {', '.join(sorted(unknown))}")

    async def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
        permissions: Annotated[frozenset[str], Depends(get_current_permissions)],
    ) -> Principal:
        if principal.is_superuser or required <= permissions:
            return principal

        raise ForbiddenException("Insufficient permissions")

    return Depends(dependency)


async def can_delegate_permissions(
    db: AsyncSession,
    principal: Principal,
    permissions: Collection[str],
) -> bool:
    """Whether a principal may hand out every one of these permissions.

    This is the escalation check only: a caller can't grant what they don't hold.
    A route that changes a role must still require ``role.update``, and one that
    assigns a role must still require ``role.assign``.

    Unregistered names are never delegable, so a typo or a removed permission
    can't slip through.
    """
    needed = set(permissions)

    if needed - all_permissions():
        return False

    if principal.is_superuser:
        return True

    held = await load_permissions(db, principal.user_id)

    return needed <= held


async def can_assign_role(db: AsyncSession, principal: Principal, role_id: int) -> bool:
    """Whether a principal may assign this role to someone.

    The escalation check for role assignment: every permission the role carries
    must be one the caller already holds. Stored names that are no longer
    registered are ignored, the same way ``load_permissions`` ignores them.
    """
    if principal.is_superuser:
        return True

    statement = select(RolePermission.permission_name).where(RolePermission.role_id == role_id)
    result = await db.execute(statement)
    carried = set(result.scalars().all()) & all_permissions()

    if not carried:
        return True

    held = await load_permissions(db, principal.user_id)

    return carried <= held
