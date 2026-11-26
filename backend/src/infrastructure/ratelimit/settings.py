"""Settings for the API rate-limit feature."""

from ..config.base import EnvSettings


class RateLimitSettings(EnvSettings):
    """Whether API routes are throttled, and the limit used when no tier row matches."""

    RATE_LIMITER_ENABLED: bool = True
    DEFAULT_RATE_LIMIT_LIMIT: int = 100
    DEFAULT_RATE_LIMIT_PERIOD: int = 60
