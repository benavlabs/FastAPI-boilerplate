"""The contributions features make to each other's extension points.

Hand-maintained until the generator exists: imports and literals only.
"""

from ..infrastructure.auth.health import limiter_readiness, sessions_readiness
from ..infrastructure.cache.health import readiness as cache_readiness
from ..infrastructure.composition import PermissionSource, RateLimitResolver, ReadinessCheck, TierDeleteGuard
from ..infrastructure.database.health import readiness as database_readiness
from ..infrastructure.taskiq.health import readiness as broker_readiness
from ..modules.rate_limit.hooks import rate_limits_reference_tier, tier_rate_limit
from ..modules.role.sources import role_permissions

PERMISSION_SOURCES: tuple[PermissionSource, ...] = (role_permissions,)
RATE_LIMIT_RESOLVERS: tuple[RateLimitResolver, ...] = (tier_rate_limit,)
TIER_DELETE_GUARDS: tuple[TierDeleteGuard, ...] = (rate_limits_reference_tier,)
READINESS_CHECKS: tuple[ReadinessCheck, ...] = (
    database_readiness,
    cache_readiness,
    limiter_readiness,
    sessions_readiness,
    broker_readiness,
)
