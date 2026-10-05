"""Core settings: environment loading and the settings every project has.

Feature settings live with their feature and are composed in ``src/wiring/settings.py``.
"""

import logging
import os
from enum import StrEnum

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from sqlalchemy.engine import URL
from starlette.config import Config

from .enums import LogFormat, LogLevel

logger = logging.getLogger(__name__)

DATABASE_NAME_RESERVED = ("/", "?", "#", "@")


def ini_value(value: str) -> str:
    """``value`` as it has to be written into an ini file, where ``%`` starts an interpolation."""
    return value.replace("%", "%%")


current_file_dir = os.path.dirname(os.path.realpath(__file__))
backend_root = os.path.abspath(os.path.join(current_file_dir, "..", "..", ".."))
project_root = os.path.abspath(os.path.join(current_file_dir, "..", "..", "..", ".."))

env_paths = [
    "/app/.env",
    os.path.join(backend_root, ".env"),
    os.path.join(project_root, ".env"),
    "/.env",
]

env_path = next((path for path in env_paths if os.path.isfile(path)), env_paths[0])

running_under_pytest = "PYTEST_VERSION" in os.environ or "PYTEST_CURRENT_TEST" in os.environ
if running_under_pytest:
    config = Config()
else:
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


SCHEMA_BUILT_ON_STARTUP = (EnvironmentOption.LOCAL, EnvironmentOption.DEVELOPMENT)
"""The environments where the app builds its schema from the models as it boots."""


def _creates_tables_by_default() -> bool:
    """Whether ``CREATE_TABLES_ON_STARTUP`` is on in the environment this process runs in."""
    environment = config("ENVIRONMENT", default=EnvironmentOption.DEVELOPMENT, cast=EnvironmentOption)

    return environment in SCHEMA_BUILT_ON_STARTUP


class DatabaseSettings(BaseSettings):
    """Database-related settings."""

    POSTGRES_USER: str = config("POSTGRES_USER", default="postgres")
    POSTGRES_PASSWORD: str = config("POSTGRES_PASSWORD", default="postgres")
    POSTGRES_SERVER: str = config("POSTGRES_SERVER", default="localhost")
    POSTGRES_PORT: int = config("POSTGRES_PORT", default=5432)
    POSTGRES_DB: str = config("POSTGRES_DB", default="postgres")
    POSTGRES_ASYNC_PREFIX: str = config("POSTGRES_ASYNC_PREFIX", default="postgresql+asyncpg://")
    CREATE_TABLES_ON_STARTUP: bool = config("CREATE_TABLES_ON_STARTUP", default=_creates_tables_by_default(), cast=bool)

    POSTGRES_POOL_SIZE: int = config("POSTGRES_POOL_SIZE", default=20, cast=int)
    POSTGRES_MAX_OVERFLOW: int = config("POSTGRES_MAX_OVERFLOW", default=0, cast=int)
    POSTGRES_POOL_PRE_PING: bool = config("POSTGRES_POOL_PRE_PING", default=True, cast=bool)
    POSTGRES_POOL_RECYCLE: int = config("POSTGRES_POOL_RECYCLE", default=-1, cast=int)

    DATABASE_URL_OVERRIDE: str | None = Field(
        default=config("DATABASE_URL", default=None),
        validation_alias="DATABASE_URL",
    )

    @property
    def DATABASE_URL(self) -> str:
        """Get the full database URL.

        Checks for DATABASE_URL environment variable first (production pattern),
        then falls back to constructing from individual components (development
        pattern), with the credentials escaped: a password containing ``@``, ``/``
        or ``#`` would otherwise produce a URL that parses as something else.

        Raises:
            ValueError: when POSTGRES_DB holds a character a URL reads as
                punctuation. SQLAlchemy parses the database name literally, so
                escaping it would connect to a differently named database.
        """
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE

        unsafe = [character for character in DATABASE_NAME_RESERVED if character in self.POSTGRES_DB]
        if unsafe:
            raise ValueError(f"POSTGRES_DB cannot contain {' or '.join(unsafe)}; rename the database or set DATABASE_URL.")

        return URL.create(
            drivername=self.POSTGRES_ASYNC_PREFIX.rstrip(":/"),
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)


class CORSSettings(BaseSettings):
    """CORS-related settings."""

    CORS_ENABLED: bool = config("CORS_ENABLED", default=True, cast=bool)
    CORS_ORIGINS: str = config("CORS_ORIGINS", default="http://localhost:3000,http://localhost:5173")
    CORS_ALLOW_CREDENTIALS: bool = config("CORS_ALLOW_CREDENTIALS", default=True, cast=bool)

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        """The origins allowed to make cross-origin requests.

        An empty setting allows none of them. Answering ``*`` instead would hand
        every site on the internet an allowance nobody asked for.
        """
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    CORS_ALLOW_METHODS: str = config("CORS_ALLOW_METHODS", default="*")
    CORS_ALLOW_HEADERS: str = config("CORS_ALLOW_HEADERS", default="*")


class CompressionSettings(BaseSettings):
    """Compression-related settings."""

    GZIP_ENABLED: bool = config("GZIP_ENABLED", default=True, cast=bool)
    GZIP_MINIMUM_SIZE: int = config("GZIP_MINIMUM_SIZE", default=1000, cast=int)


class ClientCacheSettings(BaseSettings):
    """Cache-Control headers the app sets on its own responses."""

    CLIENT_CACHE_ENABLED: bool = config("CLIENT_CACHE_ENABLED", default=True, cast=bool)
    CLIENT_CACHE_MAX_AGE: int = config("CLIENT_CACHE_MAX_AGE", default=60, cast=int)


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


class APISettings(BaseSettings):
    """API-related settings."""

    API_PREFIX: str = Field(default=config("API_PREFIX", default="/api"), validate_default=True)

    @field_validator("API_PREFIX")
    @classmethod
    def _a_prefix_the_router_can_mount(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError(f"API_PREFIX must start with '/' and must not end with '/', such as /api; got {value!r}")

        return value


class AppSettings(BaseSettings):
    """Application-related settings."""

    # Note: For API documentation, prefer using API_* fields in APIDocSettings
    APP_NAME: str = config("APP_NAME", default="FastAPI Boilerplate")
    APP_DESCRIPTION: str = config("APP_DESCRIPTION", default="")
    DEBUG: bool = config("DEBUG", default=False, cast=bool)
    VERSION: str = config("VERSION", default="0.1.0")


class SecuritySettings(BaseSettings):
    """Security validation settings, and the secret every signed value derives from."""

    SECRET_KEY: str = config("SECRET_KEY", default="insecure-secret-key-change-this")

    PRODUCTION_SECURITY_VALIDATION_ENABLED: bool = config("PRODUCTION_SECURITY_VALIDATION_ENABLED", default=True, cast=bool)
    SECURITY_HEADERS_ENABLED: bool = config("SECURITY_HEADERS_ENABLED", default=True, cast=bool)


class LoggingSettings(BaseSettings):
    """Centralized logging configuration settings."""

    LOG_LEVEL: str = config("LOG_LEVEL", default=LogLevel.INFO.value)
    LOG_FORMAT: str = Field(default=config("LOG_FORMAT", default=""), validate_default=True)

    LOG_CONSOLE_ENABLED: bool = config("LOG_CONSOLE_ENABLED", default=True, cast=bool)
    LOG_FILE_ENABLED: bool = config("LOG_FILE_ENABLED", default=False, cast=bool)
    LOG_FILE_PATH: str = config("LOG_FILE_PATH", default="logs/app.log")
    LOG_FILE_MAX_SIZE: int = config("LOG_FILE_MAX_SIZE", default=10485760, cast=int)
    LOG_FILE_BACKUP_COUNT: int = config("LOG_FILE_BACKUP_COUNT", default=5, cast=int)

    LOG_DEVELOPMENT_VERBOSE: bool = config("LOG_DEVELOPMENT_VERBOSE", default=True, cast=bool)
    LOG_PRODUCTION_OPTIMIZE: bool = config("LOG_PRODUCTION_OPTIMIZE", default=True, cast=bool)

    @field_validator("LOG_FORMAT")
    @classmethod
    def _a_format_a_formatter_implements(cls, value: str) -> str:
        chosen = value.strip().lower()
        if chosen and chosen not in set(LogFormat):
            raise ValueError(f"LOG_FORMAT must be empty or one of {', '.join(sorted(LogFormat))}; got {value!r}")

        return chosen

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


class CoreSettings(
    EnvironmentSettings,
    DatabaseSettings,
    CORSSettings,
    CompressionSettings,
    ClientCacheSettings,
    APIDocSettings,
    APISettings,
    AppSettings,
    SecuritySettings,
    LoggingSettings,
):
    """The settings every project has, whatever features it selected."""
