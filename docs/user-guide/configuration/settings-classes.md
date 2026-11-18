# Settings Classes

Settings live in `backend/src/infrastructure/config/settings.py` and are organized as Pydantic `BaseSettings` classes: each class groups related variables, and a single `Settings` class composes them all. Each class derives from `EnvSettings` in `src/infrastructure/config/base.py`, which reads the environment and `backend/.env` when the class is built: a variable set in the environment wins over the file, and the field's own default applies when neither sets it.

## Settings Architecture

```python
# src/infrastructure/config/settings.py


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
    return settings
```

Anywhere in the app:

```python
from src.infrastructure.config.settings import get_settings

settings = get_settings()
print(settings.APP_NAME)
```

## Built-in Settings Groups

The actual classes that ship with the boilerplate, all in `src/infrastructure/config/settings.py`:

| Class | Covers |
|-------|--------|
| `EnvironmentSettings` | `ENVIRONMENT` (production/staging/development/local) |
| `DatabaseSettings` | All `POSTGRES_*` vars + `DATABASE_URL` computed property |
| `CacheSettings` | `CACHE_*` (Redis + Memcached + client-side) |
| `RateLimiterSettings` | `RATE_LIMITER_*` (Redis + Memcached + defaults) |
| `CORSSettings` | `CORS_*` |
| `CompressionSettings` | `GZIP_*` |
| `APIDocSettings` | `ENABLE_DOCS_IN_PRODUCTION`, `OPENAPI_PREFIX`, `DOCS_URL`, `REDOC_URL`, `OPENAPI_URL`, and the `API_*` document metadata (title, summary, description, version, terms, contact, licence, tags) |
| `AuthSettings` | `SECRET_KEY`, `SESSION_*`, `CSRF_ENABLED`, `TRUSTED_PROXY_HOPS`, `OAUTH_*` |
| `APISettings` | `API_PREFIX` |
| `AppSettings` | `APP_NAME`, `APP_DESCRIPTION`, `VERSION`, `DEBUG` |
| `AdminSettings` | `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `DEFAULT_TIER_NAME` |
| `SQLAdminSettings` | `ADMIN_ENABLED` |
| `SecuritySettings` | `SECRET_KEY`, `PRODUCTION_SECURITY_VALIDATION_ENABLED`, `SECURITY_HEADERS_ENABLED` |
| `LoggingSettings` | All `LOG_*` |
| `TaskiqSettings` | `TASKIQ_*` (Redis + RabbitMQ + worker tuning) |
| `APIKeySettings` | `KEY_USAGE_RETENTION_DAYS` |

## Anatomy of a Settings Group

A typical class:

```python
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

    DATABASE_URL_OVERRIDE: str | None = Field(default=None, validation_alias="DATABASE_URL")

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
        """Construct the full database URL.

        Falls back to assembling from POSTGRES_* if DATABASE_URL is not set.
        """
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        return (
            f"{self.POSTGRES_ASYNC_PREFIX}{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:"
            f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
```

Key points:

- Each field is named after its variable and carries its default; the field's type is what the value is parsed to (`int`, `bool`, an enum).
- A `bool` written as text is `true`, `false`, `1` or `0` in any case, and an `int` written as text is whatever `int()` reads, so `yes` and `1.0` are refused rather than guessed at.
- Values are read when a settings class is built, so a test that sets or deletes a variable sees the change in the next `Settings()` it builds.
- A default that depends on another variable is set by a `mode="before"` model validator, which sees every value the settings are built with: `CREATE_TABLES_ON_STARTUP` follows the `ENVIRONMENT` given to the constructor or read from the environment. The `default_factory` only answers for settings built without validation.
- The environment file is read as it always was: one `NAME=value` a line, names exactly as written, values literally (no `${...}` expansion, and a `#` is part of the value).
- Use `@property` for derived values (like `DATABASE_URL`) — no need for `@computed_field` since callers always go through `get_settings()`.

## Adding Custom Settings

### Basic Custom Group

```python
# your module's settings.py
from src.infrastructure.config.base import EnvSettings


class StorageSettings(EnvSettings):
    """File-storage settings."""

    STORAGE_BACKEND: str = "local"     # "local" or "s3"
    LOCAL_STORAGE_PATH: str = "./uploads"

    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_BUCKET_NAME: str = ""
    AWS_REGION: str = "us-east-1"

    MAX_UPLOAD_SIZE_BYTES: int = 10_485_760


class Settings(
    EnvironmentSettings,
    DatabaseSettings,
    # ...existing groups...
    StorageSettings,        # add yours
):
    pass
```

Then add the matching variables to `backend/.env.example` so they're discoverable.

### Computed / Derived Values

```python
class StorageSettings(EnvSettings):
    STORAGE_BACKEND: str = "local"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_BUCKET_NAME: str = ""

    @property
    def s3_configured(self) -> bool:
        return bool(self.AWS_ACCESS_KEY_ID and self.AWS_SECRET_ACCESS_KEY and self.AWS_BUCKET_NAME)

    @property
    def storage_enabled(self) -> bool:
        if self.STORAGE_BACKEND == "local":
            return True
        if self.STORAGE_BACKEND == "s3":
            return self.s3_configured
        return False
```

### Validation

For richer validation, switch a field's value to use Pydantic validators:

```python
from pydantic import field_validator, model_validator


class StorageSettings(EnvSettings):
    STORAGE_BACKEND: str = "local"
    MAX_UPLOAD_SIZE_BYTES: int = 10_485_760

    @field_validator("MAX_UPLOAD_SIZE_BYTES")
    @classmethod
    def _check_upload_size(cls, v: int) -> int:
        if v < 1024:
            raise ValueError("MAX_UPLOAD_SIZE_BYTES must be at least 1KB")
        if v > 100 * 1024 * 1024:
            raise ValueError("MAX_UPLOAD_SIZE_BYTES cannot exceed 100MB")
        return v

    @model_validator(mode="after")
    def _check_backend(self) -> "StorageSettings":
        if self.STORAGE_BACKEND not in ("local", "s3"):
            raise ValueError(f"Unknown STORAGE_BACKEND: {self.STORAGE_BACKEND}")
        return self
```

Validators run when `Settings()` is instantiated at startup, so misconfiguration fails fast.

## Enums for Constrained Values

For options with a fixed set of valid values, define a `StrEnum` in `src/infrastructure/config/enums.py` and use it as the default:

```python
# enums.py
from enum import StrEnum


class StorageBackend(StrEnum):
    LOCAL = "local"
    S3 = "s3"


# settings.py
from .enums import StorageBackend


class StorageSettings(EnvSettings):
    STORAGE_BACKEND: str = StorageBackend.LOCAL.value
```

The boilerplate already does this for `CacheBackend`, `LogFormat`, `LogLevel`, `SessionBackend`, `TaskiqBrokerType`, and `EnvironmentOption`.

## Removing Built-in Groups

If you don't use a feature, drop the corresponding class from the `Settings` MRO:

```python
class Settings(
    EnvironmentSettings,
    DatabaseSettings,
    CORSSettings,
    AuthSettings,
    APISettings,
    AppSettings,
    LoggingSettings,
    # CacheSettings — removed
    # RateLimiterSettings — removed
    # TaskiqSettings — removed
):
    pass
```

You'll also want to:

- Remove the now-orphan code that depends on those settings (e.g. cache decorator, taskiq broker, rate limiter middleware)
- Drop the corresponding env vars from `.env.example`
- Disable startup of those subsystems in `infrastructure/app_factory.py`

## Testing Settings

The test suite uses fixtures that override settings. The general pattern:

```python
import pytest
from src.infrastructure.config.settings import Settings


@pytest.fixture
def test_settings(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("CACHE_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMITER_ENABLED", "false")
    return Settings()
```

For one-off overrides without env vars, instantiate the relevant settings class directly with kwargs:

```python
def test_storage_validation():
    with pytest.raises(ValueError, match="cannot exceed 100MB"):
        StorageSettings(MAX_UPLOAD_SIZE_BYTES=200_000_000)
```

## Best Practices

### Organization

- Group settings by **subsystem** (cache, auth, taskiq), not by environment
- Keep validation alongside the field it validates
- Add a one-line docstring per class so its purpose is obvious
- Mirror group names in `.env.example` section headers

### Security

- Validate `SECRET_KEY` length / strength when `ENVIRONMENT=production` (the boilerplate already does this via the production security validator)
- Never set a real default for credentials — leave them blank and let the validator complain
- Use `@property` to derive connection strings rather than embedding them in env vars

### Performance

- The `Settings` instance is created once at import time and shared via `get_settings()` — don't instantiate it per-request
- Keep validators cheap; they run at startup but they also run if anyone re-instantiates `Settings`

### Testing

- Use `monkeypatch.setenv(...)` to vary env vars per test
- Don't reach for the global `settings` in tests when you can pass an instance directly

## See Also

- **[Environment Variables](environment-variables.md)** — Full variable reference
- **[Docker Setup](docker-setup.md)** — How variables flow into Compose
- **[Environment-Specific](environment-specific.md)** — Recommended values per environment
