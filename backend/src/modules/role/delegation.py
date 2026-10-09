"""The escalation checks for handing out grants, which read the role tables.

A caller can never delegate a permission, or assign a role carrying one, that
they do not already hold themselves. These are only the escalation checks: a
route that changes a role must still require ``role.update``, and one that
assigns a role must still require ``role.assign``.

What the caller holds is passed in, not looked up: a credential that carries a scope holds
its owner's permissions narrowed to that scope, and the narrowing happens where the
request resolves it.
"""

from collections.abc import Collection

from crudauth import Principal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import load_permissions
from ...infrastructure.permissions import all_permissions
from ..user.crud import crud_users
from .models import RolePermission


def can_delegate_permissions(
    principal: Principal,
    permissions: Collection[str],
    held: Collection[str],
) -> bool:
    """Whether a principal holding ``held`` may hand out every one of these permissions.

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

    return needed <= set(held)


async def can_assign_role(db: AsyncSession, principal: Principal, role_id: int, held: Collection[str]) -> bool:
    """Whether a principal holding ``held`` may assign this role to someone.

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

    return carried <= set(held)


async def can_change_roles_of(db: AsyncSession, principal: Principal, user_id: int, held: Collection[str]) -> bool:
    """Whether a principal holding ``held`` may change which roles an account holds.

    Changing an account's roles is a way to take it over, so a caller may only reach an
    account weaker than their own: not a superuser, and holding nothing the caller does
    not already hold. This is the same rule a ``user.update`` holder is held to when
    editing an account.
    """
    if principal.is_superuser:
        return True

    target = await crud_users.get(db=db, id=user_id, is_deleted=False)
    if target is None:
        return False

    if target.get("is_superuser", False):
        return False

    theirs = await load_permissions(db, user_id)

    return theirs <= set(held)
