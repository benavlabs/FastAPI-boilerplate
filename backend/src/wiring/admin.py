"""The model views the admin panel registers.

Written by the generator in `tools/removal_drill.py`, which a test compares this file against.
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
