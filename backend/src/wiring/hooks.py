"""The contributions features make to each other's extension points.

Hand-maintained until the generator exists: imports and literals only.
"""

from crudauth import EmailSender

from ..infrastructure.auth.health import limiter_readiness, sessions_readiness
from ..infrastructure.cache.health import readiness as cache_readiness
from ..infrastructure.composition import (
    PermissionSource,
    RateLimitResolver,
    ReadinessCheck,
    TierDeleteGuard,
    TierDeleteRelease,
)
from ..infrastructure.database.health import readiness as database_readiness
from ..infrastructure.taskiq.email import queued_sender
from ..infrastructure.taskiq.health import readiness as broker_readiness
from ..modules.rate_limit.hooks import rate_limits_reference_tier, release_deleted_rate_limits, tier_rate_limit
from ..modules.role.sources import role_permissions

EMAIL_SENDER: EmailSender = queued_sender
PERMISSION_SOURCES: tuple[PermissionSource, ...] = (role_permissions,)
RATE_LIMIT_RESOLVERS: tuple[RateLimitResolver, ...] = (tier_rate_limit,)
TIER_DELETE_GUARDS: tuple[TierDeleteGuard, ...] = (rate_limits_reference_tier,)
TIER_DELETE_RELEASES: tuple[TierDeleteRelease, ...] = (release_deleted_rate_limits,)
CRITICAL_READINESS_CHECKS: tuple[ReadinessCheck, ...] = (
    database_readiness,
    limiter_readiness,
    sessions_readiness,
)
INFORMATIONAL_READINESS_CHECKS: tuple[ReadinessCheck, ...] = (
    cache_readiness,
    broker_readiness,
)
