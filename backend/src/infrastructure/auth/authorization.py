"""Authorization: what the caller is allowed to do.

The interface belongs to accounts; where the grants come from does not. A
superuser holds every registered permission, and everyone else holds the union of
what the wiring's permission sources return. A project that contributes no
source -- one without a role feature -- therefore lets only superusers past a
permission check, which is what the app did before roles existed.
"""

from collections.abc import Sequence
from typing import Annotated, Any

from crudauth import Principal
from crudauth.exceptions import ForbiddenException
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...wiring.hooks import PERMISSION_SOURCES
from ..composition import PermissionSource
from ..database.session import async_session
from ..permissions import all_permissions
from .dependencies import get_current_principal
from .scope import carries_a_scope, owner_is_superuser


async def load_permissions(
    db: AsyncSession,
    user_id: int,
    *,
    is_superuser: bool = False,
    sources: Sequence[PermissionSource] | None = None,
) -> frozenset[str]:
    """The permissions a user effectively holds, gathered from every source.

    Reads through the session the request already uses, so a source sees the same
    data (and the same database under test overrides) as the route it authorizes.
    Names that are not registered are ignored, so a stored grant for a permission
    the code has since dropped can't grant anything.

    Args:
        db: Database session the sources read through.
        user_id: The user whose grants to gather.
        is_superuser: When true, every registered permission is granted without a query.
        sources: The sources to ask; the wiring's when not given.

    Returns:
        The registered permission names the user holds.
    """
    registered = all_permissions()

    if is_superuser:
        return registered

    if not registered:
        return frozenset()

    granted: set[str] = set()
    for source in PERMISSION_SOURCES if sources is None else sources:
        granted.update(await source(db, user_id))

    return frozenset(granted & registered)


async def get_current_permissions(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(async_session)],
) -> frozenset[str]:
    """The current caller's effective permissions, resolved once per request.

    A credential that carries a scope holds its owner's permissions — a superuser's being
    every registered one, read from the credential's own record of that flag rather than
    from the principal, whose flag a scoped credential never carries — narrowed to that
    scope, so a scope naming nothing holds nothing. FastAPI caches
    a dependency's result for the length of a request, so however many
    ``require_permissions`` guards and route parameters ask for permissions, the sources
    are asked once.
    """
    if carries_a_scope(principal):
        held = await load_permissions(db, principal.user_id, is_superuser=owner_is_superuser(principal))

        return held & frozenset(principal.scopes)

    return await load_permissions(db, principal.user_id, is_superuser=principal.is_superuser)


def require_permissions(*needed: str) -> Any:
    """A dependency that answers 403 unless the caller holds every named permission.

    A superuser's own session passes without a lookup; a credential carrying a scope is
    held to that scope, superuser or not. Unknown names are a programming error and
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
        if (principal.is_superuser and not carries_a_scope(principal)) or required <= permissions:
            return principal

        raise ForbiddenException("Insufficient permissions")

    return Depends(dependency)
