"""The contributions features make to each other's extension points.

Hand-maintained until the generator exists: imports and literals only.
"""

from ..infrastructure.composition import PermissionSource, RateLimitResolver
from ..modules.rate_limit.hooks import tier_rate_limit
from ..modules.role.sources import role_permissions

PERMISSION_SOURCES: tuple[PermissionSource, ...] = (role_permissions,)
RATE_LIMIT_RESOLVERS: tuple[RateLimitResolver, ...] = (tier_rate_limit,)
