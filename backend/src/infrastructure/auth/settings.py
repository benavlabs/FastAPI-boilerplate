"""Settings for the accounts feature: users, sessions, CSRF, login lockout, OAuth."""

from pydantic import AliasChoices, Field

from ..config.base import EnvSettings
from ..config.enums import RateLimiterBackend, SessionBackend
from ..redis import redis_url


class AuthSettings(EnvSettings):
    """Authentication-related settings.

    Sessions have their own Redis connection. Each of its fields falls back to the
    cache's, as a default and as a validation alias, so an ``.env`` that only sets
    ``CACHE_REDIS_*`` keeps working.
    """

    SESSION_TIMEOUT_MINUTES: int = 30
    SESSION_ABSOLUTE_TIMEOUT_HOURS: int | None = None
    FRESH_SIGN_IN_SECONDS: int | None = None

    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_ATTEMPT_WINDOW_SECONDS: int = 900
    LOGIN_LOCKOUT_BASE_SECONDS: int = 300
    LOGIN_LOCKOUT_MAX_SECONDS: int = 3600
    SESSION_CLEANUP_INTERVAL_MINUTES: int = 15
    MAX_SESSIONS_PER_USER: int = 5
    SESSION_SECURE_COOKIES: bool = True
    SESSION_BACKEND: str = SessionBackend.REDIS.value

    SESSION_REDIS_DB: int = 2
    SESSION_REDIS_URL_OVERRIDE: str | None = Field(
        default=None,
        validation_alias="SESSION_REDIS_URL",
    )

    CSRF_ENABLED: bool = True

    # Number of trusted reverse proxies in front of the app. crudauth resolves the
    # client IP for login lockout from the last hop of X-Forwarded-For; 0 = the socket
    # peer (no proxy). Set to 1 behind a single nginx/Caddy, 2 if Cloudflare is also in front.
    TRUSTED_PROXY_HOPS: int = 0

    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True

    OAUTH_GOOGLE_CLIENT_ID: str = ""
    OAUTH_GOOGLE_CLIENT_SECRET: str = ""
    OAUTH_GITHUB_CLIENT_ID: str = ""
    OAUTH_GITHUB_CLIENT_SECRET: str = ""
    OAUTH_REDIRECT_BASE_URL: str = "http://localhost:8000"

    SESSION_REDIS_HOST: str = Field(
        default="localhost",
        validation_alias=AliasChoices("SESSION_REDIS_HOST", "CACHE_REDIS_HOST"),
    )
    SESSION_REDIS_PORT: int = Field(
        default=6379,
        validation_alias=AliasChoices("SESSION_REDIS_PORT", "CACHE_REDIS_PORT"),
    )
    SESSION_REDIS_PASSWORD: str | None = Field(
        default=None,
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


class LimiterBackendSettings(EnvSettings):
    """The limiter crudauth uses for login lockout, whether or not API routes are throttled."""

    RATE_LIMITER_BACKEND: str = RateLimiterBackend.REDIS.value
    RATE_LIMITER_REDIS_HOST: str = "localhost"
    RATE_LIMITER_REDIS_PORT: int = 6379
    RATE_LIMITER_REDIS_DB: int = 1
    RATE_LIMITER_REDIS_PASSWORD: str | None = None
    RATE_LIMITER_REDIS_CONNECT_TIMEOUT: int = 5
    RATE_LIMITER_REDIS_POOL_SIZE: int = 10


class FirstSuperuserSettings(EnvSettings):
    """The first superuser, created by ``scripts/create_first_superuser.py``."""

    ADMIN_NAME: str = ""
    ADMIN_EMAIL: str = ""
    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD: str = ""


class AccountsSettings(AuthSettings, LimiterBackendSettings, FirstSuperuserSettings):
    """Everything the accounts feature reads."""
