"""The escalation checks for handing out grants, which read the role tables.

A caller can never delegate a permission, or assign a role carrying one, that
they do not already hold themselves. These are only the escalation checks: a
route that changes a role must still require ``role.update``, and one that
assigns a role must still require ``role.assign``.
"""

from collections.abc import Collection

from crudauth import Principal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import load_permissions
from ...infrastructure.permissions import all_permissions
from .models import RolePermission


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
