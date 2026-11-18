"""Core settings: environment loading and the settings every project has.

Feature settings live with their feature and are composed in ``src/wiring/settings.py``.
"""

import logging
import os
from collections.abc import Mapping
from enum import StrEnum
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, EnvSettingsSource, PydanticBaseSettingsSource, SettingsConfigDict
from sqlalchemy.engine import URL
from starlette.config import Config

from .enums import EmailBackend, LogFormat, LogLevel

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

env_path = next((path for path in env_paths if os.path.isfile(path)), None)

running_under_pytest = "PYTEST_VERSION" in os.environ or "PYTEST_CURRENT_TEST" in os.environ
if running_under_pytest or env_path is None:
    if not running_under_pytest:
        logger.info("No environment file found; settings are read from the environment.")

    config = Config()
else:
    logger.info(f"Using environment file at: {env_path}")
    config = Config(env_path)


FLAG_SPELLINGS = {"true": True, "1": True, "false": False, "0": False}
"""How a flag may be written: the spellings starlette's ``Config`` casts to a bool."""


class _FileAsStarletteReadsIt(EnvSettingsSource):
    """The environment file, read as starlette's ``Config`` reads it: one ``NAME=value`` a line,
    names exactly as written, values literally, with no ``${...}`` expansion or ``#`` comments.

    Only the fields of the class being built are taken from it, so each mixin leaves the other
    mixins' names alone.
    """

    def __init__(self, settings_cls: type[BaseSettings], env_file: Any) -> None:
        self.env_file = env_file
        super().__init__(settings_cls, case_sensitive=True)

    def _load_env_vars(self) -> Mapping[str, str | None]:
        return Config(self.env_file).file_values if self.env_file else {}


class EnvSettings(BaseSettings):
    """A settings mixin that reads the environment, and the environment file, when it is built.

    The file is the one ``config`` reads, and none under pytest. The environment wins over it.
    """

    model_config = SettingsConfigDict(env_file=None if running_under_pytest else env_path)

    @field_validator("*", mode="before")
    @classmethod
    def _read_as_starlette_cast_it(cls, value: Any, info: ValidationInfo) -> Any:
        """A flag written as text is one of ``true``, ``false``, ``1`` or ``0`` in any case, and a
        number written as text is what ``int()`` reads, as when starlette's ``Config`` cast them."""
        if not isinstance(value, str) or info.field_name is None:
            return value

        annotation = cls.model_fields[info.field_name].annotation
        kinds = set(get_args(annotation)) if get_origin(annotation) in (Union, UnionType) else {annotation}
        if bool in kinds:
            if value.lower() not in FLAG_SPELLINGS:
                raise ValueError(f"{value!r} is not a flag: write true, false, 1 or 0")

            return FLAG_SPELLINGS[value.lower()]
        if int in kinds:
            return int(value)

        return value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """The constructor, then the environment, then the file read as starlette reads it."""
        env_file = getattr(dotenv_settings, "env_file", None)

        return init_settings, env_settings, _FileAsStarletteReadsIt(settings_cls, env_file), file_secret_settings


class EnvironmentOption(StrEnum):
    """Environment options for the application."""

    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    LOCAL = "local"


class EnvironmentSettings(EnvSettings):
    """Environment-related settings."""

    ENVIRONMENT: EnvironmentOption = EnvironmentOption.DEVELOPMENT


SCHEMA_BUILT_ON_STARTUP = (EnvironmentOption.LOCAL, EnvironmentOption.DEVELOPMENT)
"""The environments where the app builds its schema from the models as it boots."""


def _creates_tables_by_default(environment: str | None = None) -> bool:
    """Whether ``CREATE_TABLES_ON_STARTUP`` is on in ``environment``, or in the one the process runs in."""
    return EnvironmentOption(environment or EnvironmentSettings().ENVIRONMENT) in SCHEMA_BUILT_ON_STARTUP


class DatabaseSettings(EnvSettings):
    """Database-related settings."""

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "postgres"
    POSTGRES_ASYNC_PREFIX: str = "postgresql+asyncpg://"
    CREATE_TABLES_ON_STARTUP: bool = Field(default_factory=_creates_tables_by_default)

    POSTGRES_POOL_SIZE: int = 20
    POSTGRES_MAX_OVERFLOW: int = 0
    POSTGRES_POOL_PRE_PING: bool = True
    POSTGRES_POOL_RECYCLE: int = -1

    DATABASE_URL_OVERRIDE: str | None = Field(
        default=None,
        validation_alias="DATABASE_URL",
    )

    @model_validator(mode="before")
    @classmethod
    def _tables_follow_the_environment(cls, values: Any) -> Any:
        """Default ``CREATE_TABLES_ON_STARTUP`` from the ``ENVIRONMENT`` these settings are built with."""
        if not isinstance(values, dict) or "CREATE_TABLES_ON_STARTUP" in values:
            return values
        try:
            creates = _creates_tables_by_default(values.get("ENVIRONMENT"))
        except ValueError:
            return values

        return {**values, "CREATE_TABLES_ON_STARTUP": creates}

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


class CORSSettings(EnvSettings):
    """CORS-related settings."""

    CORS_ENABLED: bool = True
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    CORS_ALLOW_CREDENTIALS: bool = True

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        """The origins allowed to make cross-origin requests.

        An empty setting allows none of them. Answering ``*`` instead would hand
        every site on the internet an allowance nobody asked for.
        """
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    CORS_ALLOW_METHODS: str = "*"
    CORS_ALLOW_HEADERS: str = "*"


class CompressionSettings(EnvSettings):
    """Compression-related settings."""

    GZIP_ENABLED: bool = True
    GZIP_MINIMUM_SIZE: int = 1000


class ClientCacheSettings(EnvSettings):
    """Cache-Control headers the app sets on its own responses."""

    CLIENT_CACHE_ENABLED: bool = True
    CLIENT_CACHE_MAX_AGE: int = 60


class APIDocSettings(EnvSettings):
    """API documentation settings."""

    ENABLE_DOCS_IN_PRODUCTION: bool = False
    OPENAPI_PREFIX: str = ""
    DOCS_URL: str = "/docs"
    REDOC_URL: str = "/redoc"
    OPENAPI_URL: str = "/openapi.json"

    API_TITLE: str = ""
    API_SUMMARY: str = ""
    API_DESCRIPTION: str = ""
    API_VERSION: str = ""
    API_TERMS_OF_SERVICE: str = ""

    API_CONTACT_NAME: str = ""
    API_CONTACT_URL: str = ""
    API_CONTACT_EMAIL: str = ""

    API_LICENSE_NAME: str = ""
    API_LICENSE_URL: str = ""
    API_LICENSE_IDENTIFIER: str = ""

    API_TAGS_METADATA: str = "[]"


class APISettings(EnvSettings):
    """API-related settings."""

    API_PREFIX: str = Field(default="/api", validate_default=True)

    @field_validator("API_PREFIX")
    @classmethod
    def _a_prefix_the_router_can_mount(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError(f"API_PREFIX must start with '/' and must not end with '/', such as /api; got {value!r}")

        return value


class AppSettings(EnvSettings):
    """Application-related settings."""

    # Note: For API documentation, prefer using API_* fields in APIDocSettings
    APP_NAME: str = "FastAPI Boilerplate"
    APP_DESCRIPTION: str = ""
    DEBUG: bool = False
    VERSION: str = "0.1.0"


class EmailSettings(EnvSettings):
    """How the account emails are delivered, and who they come from."""

    EMAIL_BACKEND: str = EmailBackend.CONSOLE.value
    EMAIL_FROM: str = "no-reply@localhost"
    EMAIL_FROM_NAME: str = ""

    FRONTEND_URL: str = "http://localhost:3000"

    EMAIL_SMTP_HOST: str = ""
    EMAIL_SMTP_PORT: int = 587
    EMAIL_SMTP_USER: str = ""
    EMAIL_SMTP_PASSWORD: str = ""
    EMAIL_SMTP_STARTTLS: bool = True
    EMAIL_SMTP_TIMEOUT_SECONDS: int = 10


class SecuritySettings(EnvSettings):
    """Security validation settings, and the secret every signed value derives from."""

    SECRET_KEY: str = "insecure-secret-key-change-this"

    PRODUCTION_SECURITY_VALIDATION_ENABLED: bool = True
    SECURITY_HEADERS_ENABLED: bool = True


class LoggingSettings(EnvSettings):
    """Centralized logging configuration settings."""

    LOG_LEVEL: str = LogLevel.INFO.value
    LOG_FORMAT: str = Field(default="", validate_default=True)

    LOG_CONSOLE_ENABLED: bool = True
    LOG_FILE_ENABLED: bool = False
    LOG_FILE_PATH: str = "logs/app.log"
    LOG_FILE_MAX_SIZE: int = 10485760
    LOG_FILE_BACKUP_COUNT: int = 5

    LOG_DEVELOPMENT_VERBOSE: bool = True
    LOG_PRODUCTION_OPTIMIZE: bool = True

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
    EmailSettings,
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
