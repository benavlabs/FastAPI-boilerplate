"""Settings for the API rate-limit feature."""

from pydantic_settings import BaseSettings

from ..config.base import config


class RateLimitSettings(BaseSettings):
    """Whether API routes are throttled, and the limit used when no tier row matches."""

    RATE_LIMITER_ENABLED: bool = config("RATE_LIMITER_ENABLED", default=True, cast=bool)
    DEFAULT_RATE_LIMIT_LIMIT: int = config("DEFAULT_RATE_LIMIT_LIMIT", default=100, cast=int)
    DEFAULT_RATE_LIMIT_PERIOD: int = config("DEFAULT_RATE_LIMIT_PERIOD", default=60, cast=int)
