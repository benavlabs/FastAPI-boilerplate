"""Initialize all modules and models to ensure SQLAlchemy registration."""

from .api_keys.models import APIKey, KeyPermission, KeyUsage
from .rate_limit.models import RateLimit
from .role.models import Role, RolePermission, UserRole
from .role.permission_registry import discover_permissions
from .tier.models import Tier
from .user.models import User

discover_permissions("src.modules")

__all__ = [
    "User",
    "Tier",
    "RateLimit",
    "APIKey",
    "KeyUsage",
    "KeyPermission",
    "Role",
    "RolePermission",
    "UserRole",
]