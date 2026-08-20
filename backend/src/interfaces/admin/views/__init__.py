"""SQLAdmin model views for the admin interface."""

from sqladmin import Admin
from .role_permissions import RolePermissionAdmin
from .roles import RoleAdmin
from .user_roles import UserRoleAdmin
from .tiers import TierAdmin
from .users import UserAdmin

__all__ = [
    "UserAdmin",
    "TierAdmin",
    "RoleAdmin",
    "RolePermissionAdmin",
    "UserRoleAdmin",
    "register_admin_views",
]


def register_admin_views(admin: Admin) -> None:
    """Register all model views with the admin interface."""
    admin.add_view(UserAdmin)
    admin.add_view(RoleAdmin)
    admin.add_view(RolePermissionAdmin)
    admin.add_view(UserRoleAdmin)
    admin.add_view(TierAdmin)
