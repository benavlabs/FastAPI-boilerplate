"""The model views the admin panel registers.

Hand-maintained until the generator exists.
"""

from ..modules.role.admin import RoleAdmin, RolePermissionAdmin, UserRoleAdmin
from ..modules.tier.admin import TierAdmin
from ..modules.user.admin import UserAdmin

ADMIN_VIEWS: tuple[type, ...] = (
    UserAdmin,
    TierAdmin,
    RoleAdmin,
    RolePermissionAdmin,
    UserRoleAdmin,
)
