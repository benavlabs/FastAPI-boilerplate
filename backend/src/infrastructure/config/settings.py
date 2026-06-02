import logging
import os
from enum import StrEnum

from pydantic_settings import BaseSettings
from starlette.config import Config

from .enums import CacheBackend, LogFormat, LogLevel, SessionBackend, TaskiqBrokerType

logger = logging.getLogger(__name__)

current_file_dir = os.path.dirname(os.path.realpath(__file__))
project_root = os.path.abspath(os.path.join(current_file_dir, "..", "..", "..", ".."))

env_paths = [
    "/app/.env",
    os.path.join(project_root, ".env"),
    "/.env",
]

env_path = next((path for path in env_paths if os.path.isfile(path)), env_paths[0])
logger.info(f"Using environment file at: {env_path}")

config = Config(env_path)


class EnvironmentOption(StrEnum):
    """Environment options for the application."""

    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    LOCAL = "local"


class EnvironmentSettings(BaseSettings):
    """Environment-related settings."""

    ENVIRONMENT: EnvironmentOption = config("ENVIRONMENT", default=EnvironmentOption.DEVELOPMENT, cast=EnvironmentOption)


class DatabaseSettings(BaseSettings):
    """Database-related settings."""

    POSTGRES_USER: str = config("POSTGRES_USER", default="postgres")
    POSTGRES_PASSWORD: str = config("POSTGRES_PASSWORD", default="postgres")
    POSTGRES_SERVER: str = config("POSTGRES_SERVER", default="localhost")
    POSTGRES_PORT: int = config("POSTGRES_PORT", default=5432)
    POSTGRES_DB: str = config("POSTGRES_DB", default="postgres")
    POSTGRES_SYNC_PREFIX: str = config("POSTGRES_SYNC_PREFIX", default="postgresql://")
    POSTGRES_ASYNC_PREFIX: str = config("POSTGRES_ASYNC_PREFIX", default="postgresql+asyncpg://")
    CREATE_TABLES_ON_STARTUP: bool = config("CREATE_TABLES_ON_STARTUP", default=True, cast=bool)

    POSTGRES_POOL_SIZE: int = config("POSTGRES_POOL_SIZE", default=20, cast=int)
    POSTGRES_MAX_OVERFLOW: int = config("POSTGRES_MAX_OVERFLOW", default=0, cast=int)

    @property
    def DATABASE_URL(self) -> str:
        """Get the full database URL.

        Checks for DATABASE_URL environment variable first (production pattern),
        then falls back to constructing from individual components (development pattern).
        """
        direct_url = config("DATABASE_URL", default=None)
        if direct_url:
            return direct_url

        return (
            f"{self.POSTGRES_ASYNC_PREFIX}{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:"
            f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


class CacheSettings(BaseSettings):
    """Cache-related settings.

    This class defines settings for cache connections and behavior across
    the application.

    Attributes:
        CACHE_ENABLED: Whether to enable caching. Default is True.
        CACHE_BACKEND: The cache backend to use. Default is "memcached".

        # Memcached settings
        CACHE_MEMCACHED_HOST: Memcached server hostname. Default is "localhost".
        CACHE_MEMCACHED_PORT: Memcached server port. Default is 11211.
        CACHE_MEMCACHED_POOL_SIZE: Maximum number of connections in the pool. Default is 10.
        CACHE_MEMCACHED_CONNECT_TIMEOUT: Connection timeout in seconds. Default is 5.
            Note: This is not currently used by aiomcache.Client but is
            kept for API consistency with other cache backends.

        # Redis settings
        CACHE_REDIS_HOST: Redis server hostname. Default is "localhost".
        CACHE_REDIS_PORT: Redis server port. Default is 6379.
        CACHE_REDIS_DB: Redis database number. Default is 0.
        CACHE_REDIS_PASSWORD: Redis server password. Default is None.
        CACHE_REDIS_CONNECT_TIMEOUT: Connection timeout in seconds. Default is 5.
        CACHE_REDIS_POOL_SIZE: Maximum number of connections in the pool. Default is 10.

        DEFAULT_CACHE_EXPIRATION: Default expiration time for cache entries in seconds.
            Default is 3600 (1 hour).
    """

    CACHE_ENABLED: bool = config("CACHE_ENABLED", default=True, cast=bool)
    CACHE_BACKEND: str = config("CACHE_BACKEND", default=CacheBackend.MEMCACHED.value)

    CACHE_MEMCACHED_HOST: str = config("CACHE_MEMCACHED_HOST", default="localhost")
    CACHE_MEMCACHED_PORT: int = config("CACHE_MEMCACHED_PORT", default=11211, cast=int)
    CACHE_MEMCACHED_POOL_SIZE: int = config("CACHE_MEMCACHED_POOL_SIZE", default=10, cast=int)
    CACHE_MEMCACHED_CONNECT_TIMEOUT: int = config("CACHE_MEMCACHED_CONNECT_TIMEOUT", default=5, cast=int)

    CACHE_REDIS_HOST: str = config("CACHE_REDIS_HOST", default="localhost")
    CACHE_REDIS_PORT: int = config("CACHE_REDIS_PORT", default=6379, cast=int)
    CACHE_REDIS_DB: int = config("CACHE_REDIS_DB", default=0, cast=int)
    CACHE_REDIS_PASSWORD: str | None = config("CACHE_REDIS_PASSWORD", default=None)
    CACHE_REDIS_CONNECT_TIMEOUT: int = config("CACHE_REDIS_CONNECT_TIMEOUT", default=5, cast=int)
    CACHE_REDIS_POOL_SIZE: int = config("CACHE_REDIS_POOL_SIZE", default=10, cast=int)

    DEFAULT_CACHE_EXPIRATION: int = config("DEFAULT_CACHE_EXPIRATION", default=3600, cast=int)

    CLIENT_CACHE_ENABLED: bool = config("CLIENT_CACHE_ENABLED", default=True, cast=bool)
    CLIENT_CACHE_MAX_AGE: int = config("CLIENT_CACHE_MAX_AGE", default=60, cast=int)


class RateLimiterSettings(BaseSettings):
    """Rate limiter settings.

    This class defines settings for rate limiting connections and behavior across
    the application.

    Attributes:
        RATE_LIMITER_ENABLED: Whether to enable rate limiting. Default is True.
        RATE_LIMITER_BACKEND: The rate limiter backend to use. Default is "memcached".
        RATE_LIMITER_FAIL_OPEN: Whether to fail open (allow requests) when errors occur. Default is True.

        # Default rate limit settings
        DEFAULT_RATE_LIMIT_LIMIT: Default number of requests allowed. Default is 100.
        DEFAULT_RATE_LIMIT_PERIOD: Default period in seconds. Default is 60.

        # Memcached settings
        RATE_LIMITER_MEMCACHED_HOST: Memcached server hostname. Default is "localhost".
        RATE_LIMITER_MEMCACHED_PORT: Memcached server port. Default is 11211.
        RATE_LIMITER_MEMCACHED_POOL_SIZE: Maximum number of connections in the pool. Default is 10.

        # Redis settings
        RATE_LIMITER_REDIS_HOST: Redis server hostname. Default is "localhost".
        RATE_LIMITER_REDIS_PORT: Redis server port. Default is 6379.
        RATE_LIMITER_REDIS_DB: Redis database number. Default is 1.
        RATE_LIMITER_REDIS_PASSWORD: Redis server password. Default is None.
        RATE_LIMITER_REDIS_CONNECT_TIMEOUT: Connection timeout in seconds. Default is 5.
        RATE_LIMITER_REDIS_POOL_SIZE: Maximum number of connections in the pool. Default is 10.
    """

    RATE_LIMITER_ENABLED: bool = config("RATE_LIMITER_ENABLED", default=True, cast=bool)
    RATE_LIMITER_BACKEND: str = config("RATE_LIMITER_BACKEND", default=CacheBackend.MEMCACHED.value)
    RATE_LIMITER_FAIL_OPEN: bool = config("RATE_LIMITER_FAIL_OPEN", default=True, cast=bool)

    DEFAULT_RATE_LIMIT_LIMIT: int = config("DEFAULT_RATE_LIMIT_LIMIT", default=100, cast=int)
    DEFAULT_RATE_LIMIT_PERIOD: int = config("DEFAULT_RATE_LIMIT_PERIOD", default=60, cast=int)

    RATE_LIMITER_MEMCACHED_HOST: str = config("RATE_LIMITER_MEMCACHED_HOST", default="localhost")
    RATE_LIMITER_MEMCACHED_PORT: int = config("RATE_LIMITER_MEMCACHED_PORT", default=11211, cast=int)
    RATE_LIMITER_MEMCACHED_POOL_SIZE: int = config("RATE_LIMITER_MEMCACHED_POOL_SIZE", default=10, cast=int)

    RATE_LIMITER_REDIS_HOST: str = config("RATE_LIMITER_REDIS_HOST", default="localhost")
    RATE_LIMITER_REDIS_PORT: int = config("RATE_LIMITER_REDIS_PORT", default=6379, cast=int)
    RATE_LIMITER_REDIS_DB: int = config("RATE_LIMITER_REDIS_DB", default=1, cast=int)
    RATE_LIMITER_REDIS_PASSWORD: str | None = config("RATE_LIMITER_REDIS_PASSWORD", default=None)
    RATE_LIMITER_REDIS_CONNECT_TIMEOUT: int = config("RATE_LIMITER_REDIS_CONNECT_TIMEOUT", default=5, cast=int)
    RATE_LIMITER_REDIS_POOL_SIZE: int = config("RATE_LIMITER_REDIS_POOL_SIZE", default=10, cast=int)


class CORSSettings(BaseSettings):
    """CORS-related settings."""

    CORS_ENABLED: bool = config("CORS_ENABLED", default=True, cast=bool)
    CORS_ORIGINS: str = config("CORS_ORIGINS", default="*")
    CORS_ALLOW_CREDENTIALS: bool = config("CORS_ALLOW_CREDENTIALS", default=True, cast=bool)

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        """Get CORS origins as a list."""
        if not self.CORS_ORIGINS:
            return ["*"]
        return [x.strip() for x in self.CORS_ORIGINS.split(",") if x.strip()]

    CORS_ALLOW_METHODS: str = config("CORS_ALLOW_METHODS", default="*")
    CORS_ALLOW_HEADERS: str = config("CORS_ALLOW_HEADERS", default="*")


class CompressionSettings(BaseSettings):
    """Compression-related settings."""

    GZIP_ENABLED: bool = config("GZIP_ENABLED", default=True, cast=bool)
    GZIP_MINIMUM_SIZE: int = config("GZIP_MINIMUM_SIZE", default=1000, cast=int)


class APIDocSettings(BaseSettings):
    """API documentation settings."""

    ENABLE_DOCS_IN_PRODUCTION: bool = config("ENABLE_DOCS_IN_PRODUCTION", default=False, cast=bool)
    OPENAPI_PREFIX: str = config("OPENAPI_PREFIX", default="")
    DOCS_URL: str = config("DOCS_URL", default="/docs")
    REDOC_URL: str = config("REDOC_URL", default="/redoc")
    OPENAPI_URL: str = config("OPENAPI_URL", default="/openapi.json")

    API_TITLE: str = config("API_TITLE", default="")
    API_SUMMARY: str = config("API_SUMMARY", default="")
    API_DESCRIPTION: str = config("API_DESCRIPTION", default="")
    API_VERSION: str = config("API_VERSION", default="")
    API_TERMS_OF_SERVICE: str = config("API_TERMS_OF_SERVICE", default="")

    API_CONTACT_NAME: str = config("API_CONTACT_NAME", default="")
    API_CONTACT_URL: str = config("API_CONTACT_URL", default="")
    API_CONTACT_EMAIL: str = config("API_CONTACT_EMAIL", default="")

    API_LICENSE_NAME: str = config("API_LICENSE_NAME", default="")
    API_LICENSE_URL: str = config("API_LICENSE_URL", default="")
    API_LICENSE_IDENTIFIER: str = config("API_LICENSE_IDENTIFIER", default="")

    API_TAGS_METADATA: str = config("API_TAGS_METADATA", default="[]")


class AuthSettings(BaseSettings):
    """Authentication-related settings."""

    SECRET_KEY: str = config("SECRET_KEY", default="insecure-secret-key-change-this")
    ALGORITHM: str = config("ALGORITHM", default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = config("ACCESS_TOKEN_EXPIRE_MINUTES", default=30, cast=int)
    REFRESH_TOKEN_EXPIRE_DAYS: int = config("REFRESH_TOKEN_EXPIRE_DAYS", default=7, cast=int)

    SESSION_TIMEOUT_MINUTES: int = config("SESSION_TIMEOUT_MINUTES", default=30, cast=int)
    SESSION_CLEANUP_INTERVAL_MINUTES: int = config("SESSION_CLEANUP_INTERVAL_MINUTES", default=15, cast=int)
    MAX_SESSIONS_PER_USER: int = config("MAX_SESSIONS_PER_USER", default=5, cast=int)
    SESSION_SECURE_COOKIES: bool = config("SESSION_SECURE_COOKIES", default=True, cast=bool)
    SESSION_BACKEND: str = config("SESSION_BACKEND", default=SessionBackend.REDIS.value)
    SESSION_COOKIE_MAX_AGE: int = config("SESSION_COOKIE_MAX_AGE", default=86400, cast=int)

    CSRF_ENABLED: bool = config("CSRF_ENABLED", default=True, cast=bool)

    LOGIN_MAX_ATTEMPTS: int = config("LOGIN_MAX_ATTEMPTS", default=5, cast=int)
    LOGIN_WINDOW_MINUTES: int = config("LOGIN_WINDOW_MINUTES", default=15, cast=int)

    OAUTH_GOOGLE_CLIENT_ID: str = config("OAUTH_GOOGLE_CLIENT_ID", default="")
    OAUTH_GOOGLE_CLIENT_SECRET: str = config("OAUTH_GOOGLE_CLIENT_SECRET", default="")
    OAUTH_GITHUB_CLIENT_ID: str = config("OAUTH_GITHUB_CLIENT_ID", default="")
    OAUTH_GITHUB_CLIENT_SECRET: str = config("OAUTH_GITHUB_CLIENT_SECRET", default="")
    OAUTH_REDIRECT_BASE_URL: str = config("OAUTH_REDIRECT_BASE_URL", default="http://localhost:8000")


class APISettings(BaseSettings):
    """API-related settings."""

    API_PREFIX: str = "/api"


class AppSettings(BaseSettings):
    """Application-related settings."""

    # Note: For API documentation, prefer using API_* fields in APIDocSettings
    APP_NAME: str = config("APP_NAME", default="FastAPI Boilerplate")
    APP_DESCRIPTION: str = config("APP_DESCRIPTION", default="Modular FastAPI starter")
    DEBUG: bool = config("DEBUG", default=False, cast=bool)
    VERSION: str = config("VERSION", default="0.1.0")
    CONTACT_NAME: str = config("CONTACT_NAME", default="Support")
    CONTACT_EMAIL: str = config("CONTACT_EMAIL", default="support@example.com")
    LICENSE_NAME: str = config("LICENSE_NAME", default="All rights reserved.")


class AdminSettings(BaseSettings):
    """Admin user settings for initial setup."""

    ADMIN_NAME: str = config("ADMIN_NAME", default="")
    ADMIN_EMAIL: str = config("ADMIN_EMAIL", default="")
    ADMIN_USERNAME: str = config("ADMIN_USERNAME", default="")
    ADMIN_PASSWORD: str = config("ADMIN_PASSWORD", default="")
    DEFAULT_TIER_NAME: str = config("DEFAULT_TIER_NAME", default="free")


class SQLAdminSettings(BaseSettings):
    """SQLAdmin interface settings."""

    ADMIN_ENABLED: bool = config("ADMIN_ENABLED", default=True, cast=bool)


class SecuritySettings(BaseSettings):
    """Security validation settings."""

    PRODUCTION_SECURITY_VALIDATION_ENABLED: bool = config("PRODUCTION_SECURITY_VALIDATION_ENABLED", default=True, cast=bool)
    PRODUCTION_SECURITY_STRICT_MODE: bool = config("PRODUCTION_SECURITY_STRICT_MODE", default=False, cast=bool)
    SECURITY_HEADERS_ENABLED: bool = config("SECURITY_HEADERS_ENABLED", default=True, cast=bool)


class LoggingSettings(BaseSettings):
    """Centralized logging configuration settings."""

    LOG_LEVEL: str = config("LOG_LEVEL", default=LogLevel.INFO.value)
    LOG_FORMAT: str = config("LOG_FORMAT", default=LogFormat.STRUCTURED.value)

    LOG_CONSOLE_ENABLED: bool = config("LOG_CONSOLE_ENABLED", default=True, cast=bool)
    LOG_FILE_ENABLED: bool = config("LOG_FILE_ENABLED", default=False, cast=bool)
    LOG_FILE_PATH: str = config("LOG_FILE_PATH", default="logs/app.log")
    LOG_FILE_MAX_SIZE: int = config("LOG_FILE_MAX_SIZE", default=10485760, cast=int)
    LOG_FILE_BACKUP_COUNT: int = config("LOG_FILE_BACKUP_COUNT", default=5, cast=int)

    LOG_CORRELATION_ID: bool = config("LOG_CORRELATION_ID", default=True, cast=bool)
    LOG_STRUCTURED_CONTEXT: bool = config("LOG_STRUCTURED_CONTEXT", default=True, cast=bool)
    LOG_PERFORMANCE_METRICS: bool = config("LOG_PERFORMANCE_METRICS", default=False, cast=bool)

    LOG_SQL_QUERIES: bool = config("LOG_SQL_QUERIES", default=False, cast=bool)
    LOG_INCLUDE_STACKTRACE: bool = config("LOG_INCLUDE_STACKTRACE", default=True, cast=bool)

    LOG_DEVELOPMENT_VERBOSE: bool = config("LOG_DEVELOPMENT_VERBOSE", default=True, cast=bool)
    LOG_PRODUCTION_OPTIMIZE: bool = config("LOG_PRODUCTION_OPTIMIZE", default=True, cast=bool)

    @property
    def LOG_LEVEL_INT(self) -> int:
        """Convert string log level to integer."""
        level_map = {
            LogLevel.DEBUG.value: logging.DEBUG,
            LogLevel.INFO.value: logging.INFO,
            LogLevel.WARNING.value: logging.WARNING,
            LogLevel.ERROR.value: logging.ERROR,
            LogLevel.CRITICAL.value: logging.CRITICAL,
        }
        return level_map.get(self.LOG_LEVEL.upper(), logging.INFO)


class TaskiqSettings(BaseSettings):
    """Taskiq async task queue settings."""

    TASKIQ_ENABLED: bool = config("TASKIQ_ENABLED", default=True, cast=bool)
    TASKIQ_BROKER_TYPE: str = config("TASKIQ_BROKER_TYPE", default=TaskiqBrokerType.REDIS.value)

    TASKIQ_REDIS_HOST: str = config("TASKIQ_REDIS_HOST", default="localhost")
    TASKIQ_REDIS_PORT: int = config("TASKIQ_REDIS_PORT", default=6379, cast=int)
    TASKIQ_REDIS_DB: int = config("TASKIQ_REDIS_DB", default=3, cast=int)
    TASKIQ_REDIS_PASSWORD: str | None = config("TASKIQ_REDIS_PASSWORD", default=None)

    TASKIQ_RABBITMQ_HOST: str = config("TASKIQ_RABBITMQ_HOST", default="localhost")
    TASKIQ_RABBITMQ_PORT: int = config("TASKIQ_RABBITMQ_PORT", default=5672, cast=int)
    TASKIQ_RABBITMQ_USER: str = config("TASKIQ_RABBITMQ_USER", default="guest")
    TASKIQ_RABBITMQ_PASSWORD: str = config("TASKIQ_RABBITMQ_PASSWORD", default="guest")
    TASKIQ_RABBITMQ_VHOST: str = config("TASKIQ_RABBITMQ_VHOST", default="/")

    TASKIQ_WORKER_CONCURRENCY: int = config("TASKIQ_WORKER_CONCURRENCY", default=2, cast=int)
    TASKIQ_MAX_TASKS_PER_WORKER: int = config("TASKIQ_MAX_TASKS_PER_WORKER", default=1000, cast=int)

    @property
    def TASKIQ_BROKER_URL(self) -> str:
        """Generate broker URL based on configured backend."""
        if self.TASKIQ_BROKER_TYPE == TaskiqBrokerType.REDIS.value:
            password_part = f":{self.TASKIQ_REDIS_PASSWORD}@" if self.TASKIQ_REDIS_PASSWORD else ""
            return f"redis://{password_part}{self.TASKIQ_REDIS_HOST}:{self.TASKIQ_REDIS_PORT}/{self.TASKIQ_REDIS_DB}"
        elif self.TASKIQ_BROKER_TYPE == TaskiqBrokerType.RABBITMQ.value:
            vhost = self.TASKIQ_RABBITMQ_VHOST
            if vhost.startswith("/"):
                vhost = vhost[1:]
            return f"amqp://{self.TASKIQ_RABBITMQ_USER}:{self.TASKIQ_RABBITMQ_PASSWORD}@{self.TASKIQ_RABBITMQ_HOST}:{self.TASKIQ_RABBITMQ_PORT}/{vhost}"
        else:
            raise ValueError(f"Unsupported broker type: {self.TASKIQ_BROKER_TYPE}")


class Settings(
    EnvironmentSettings,
    DatabaseSettings,
    CacheSettings,
    RateLimiterSettings,
    CORSSettings,
    CompressionSettings,
    APIDocSettings,
    AuthSettings,
    APISettings,
    AppSettings,
    AdminSettings,
    SQLAdminSettings,
    SecuritySettings,
    LoggingSettings,
    TaskiqSettings,
):
    """Main settings class that combines all setting categories."""

    pass


settings = Settings()


def get_settings() -> Settings:
    """Get application settings.

    Returns:
        The application settings.
    """
    return settings
