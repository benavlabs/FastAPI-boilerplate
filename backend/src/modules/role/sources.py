"""Where rbac's grants come from: the roles assigned to a user.

Contributed to ``PERMISSION_SOURCES``, so the authorization checks never import
this module and a project without rbac simply has one fewer source.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.permissions import all_permissions
from .models import RolePermission, UserRole


async def role_permissions(db: AsyncSession, user_id: int) -> frozenset[str]:
    """The permission names the user's roles carry."""
    statement = (
        select(RolePermission.permission_name)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(
            UserRole.user_id == user_id,
            RolePermission.permission_name.in_(all_permissions()),
        )
    )
    result = await db.execute(statement)

    return frozenset(result.scalars().all())
