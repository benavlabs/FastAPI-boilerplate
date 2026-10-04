"""Settings for the accounts feature: users, sessions, CSRF, login lockout, OAuth."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

from ..config.base import config
from ..config.enums import RateLimiterBackend, SessionBackend
from ..redis import redis_url


class AuthSettings(BaseSettings):
    """Authentication-related settings.

    Sessions have their own Redis connection. Each of its fields falls back to the
    cache's, as a default and as a validation alias, so an ``.env`` that only sets
    ``CACHE_REDIS_*`` keeps working.
    """

    SESSION_TIMEOUT_MINUTES: int = config("SESSION_TIMEOUT_MINUTES", default=30, cast=int)
    SESSION_CLEANUP_INTERVAL_MINUTES: int = config("SESSION_CLEANUP_INTERVAL_MINUTES", default=15, cast=int)
    MAX_SESSIONS_PER_USER: int = config("MAX_SESSIONS_PER_USER", default=5, cast=int)
    SESSION_SECURE_COOKIES: bool = config("SESSION_SECURE_COOKIES", default=True, cast=bool)
    SESSION_BACKEND: str = config("SESSION_BACKEND", default=SessionBackend.REDIS.value)

    SESSION_REDIS_DB: int = config("SESSION_REDIS_DB", default=2, cast=int)
    SESSION_REDIS_URL_OVERRIDE: str | None = Field(
        default=config("SESSION_REDIS_URL", default=None),
        validation_alias="SESSION_REDIS_URL",
    )

    CSRF_ENABLED: bool = config("CSRF_ENABLED", default=True, cast=bool)

    # Number of trusted reverse proxies in front of the app. crudauth resolves the
    # client IP for login lockout from the last hop of X-Forwarded-For; 0 = the socket
    # peer (no proxy). Set to 1 behind a single nginx/Caddy, 2 if Cloudflare is also in front.
    TRUSTED_PROXY_HOPS: int = config("TRUSTED_PROXY_HOPS", default=0, cast=int)

    PASSWORD_MIN_LENGTH: int = config("PASSWORD_MIN_LENGTH", default=8, cast=int)
    PASSWORD_REQUIRE_UPPERCASE: bool = config("PASSWORD_REQUIRE_UPPERCASE", default=True, cast=bool)
    PASSWORD_REQUIRE_LOWERCASE: bool = config("PASSWORD_REQUIRE_LOWERCASE", default=True, cast=bool)
    PASSWORD_REQUIRE_DIGIT: bool = config("PASSWORD_REQUIRE_DIGIT", default=True, cast=bool)
    PASSWORD_REQUIRE_SPECIAL: bool = config("PASSWORD_REQUIRE_SPECIAL", default=True, cast=bool)

    OAUTH_GOOGLE_CLIENT_ID: str = config("OAUTH_GOOGLE_CLIENT_ID", default="")
    OAUTH_GOOGLE_CLIENT_SECRET: str = config("OAUTH_GOOGLE_CLIENT_SECRET", default="")
    OAUTH_GITHUB_CLIENT_ID: str = config("OAUTH_GITHUB_CLIENT_ID", default="")
    OAUTH_GITHUB_CLIENT_SECRET: str = config("OAUTH_GITHUB_CLIENT_SECRET", default="")
    OAUTH_REDIRECT_BASE_URL: str = config("OAUTH_REDIRECT_BASE_URL", default="http://localhost:8000")

    SESSION_REDIS_HOST: str = Field(
        default=config("SESSION_REDIS_HOST", default=config("CACHE_REDIS_HOST", default="localhost")),
        validation_alias=AliasChoices("SESSION_REDIS_HOST", "CACHE_REDIS_HOST"),
    )
    SESSION_REDIS_PORT: int = Field(
        default=config("SESSION_REDIS_PORT", default=config("CACHE_REDIS_PORT", default=6379), cast=int),
        validation_alias=AliasChoices("SESSION_REDIS_PORT", "CACHE_REDIS_PORT"),
    )
    SESSION_REDIS_PASSWORD: str | None = Field(
        default=config("SESSION_REDIS_PASSWORD", default=config("CACHE_REDIS_PASSWORD", default=None)),
        validation_alias=AliasChoices("SESSION_REDIS_PASSWORD", "CACHE_REDIS_PASSWORD"),
    )

    @property
    def SESSION_REDIS_URL(self) -> str:
        """SESSION_REDIS_URL when set, otherwise the session Redis connection on SESSION_REDIS_DB."""
        if self.SESSION_REDIS_URL_OVERRIDE:
            return self.SESSION_REDIS_URL_OVERRIDE

        return redis_url(
            self.SESSION_REDIS_HOST,
            self.SESSION_REDIS_PORT,
            self.SESSION_REDIS_DB,
            self.SESSION_REDIS_PASSWORD,
        )


class LimiterBackendSettings(BaseSettings):
    """The limiter crudauth uses for login lockout, whether or not API routes are throttled."""

    RATE_LIMITER_BACKEND: str = config("RATE_LIMITER_BACKEND", default=RateLimiterBackend.REDIS.value)
    RATE_LIMITER_REDIS_HOST: str = config("RATE_LIMITER_REDIS_HOST", default="localhost")
    RATE_LIMITER_REDIS_PORT: int = config("RATE_LIMITER_REDIS_PORT", default=6379, cast=int)
    RATE_LIMITER_REDIS_DB: int = config("RATE_LIMITER_REDIS_DB", default=1, cast=int)
    RATE_LIMITER_REDIS_PASSWORD: str | None = config("RATE_LIMITER_REDIS_PASSWORD", default=None)
    RATE_LIMITER_REDIS_CONNECT_TIMEOUT: int = config("RATE_LIMITER_REDIS_CONNECT_TIMEOUT", default=5, cast=int)
    RATE_LIMITER_REDIS_POOL_SIZE: int = config("RATE_LIMITER_REDIS_POOL_SIZE", default=10, cast=int)


class FirstSuperuserSettings(BaseSettings):
    """The first superuser, created by ``scripts/create_first_superuser.py``."""

    ADMIN_NAME: str = config("ADMIN_NAME", default="")
    ADMIN_EMAIL: str = config("ADMIN_EMAIL", default="")
    ADMIN_USERNAME: str = config("ADMIN_USERNAME", default="")
    ADMIN_PASSWORD: str = config("ADMIN_PASSWORD", default="")


class AccountsSettings(AuthSettings, LimiterBackendSettings, FirstSuperuserSettings):
    """Everything the accounts feature reads."""
