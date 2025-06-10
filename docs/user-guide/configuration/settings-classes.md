# Settings Classes

Learn how Python settings classes validate, structure, and organize your application configuration. The boilerplate uses Pydantic's `BaseSettings` for type-safe configuration management.

## Settings Architecture

The main `Settings` class inherits from multiple specialized setting groups:

```python
# src/app/core/config.py
class Settings(
    AppSettings,
    PostgresSettings, 
    CryptSettings,
    FirstUserSettings,
    RedisCacheSettings,
    ClientSideCacheSettings,
    RedisQueueSettings,
    RedisRateLimiterSettings,
    DefaultRateLimitSettings,
    EnvironmentSettings,
):
    pass

# Single instance used throughout the app
settings = Settings()
```

## Built-in Settings Groups

### Application Settings
Basic app metadata and configuration:

```python
class AppSettings(BaseSettings):
    APP_NAME: str = "FastAPI"
    APP_DESCRIPTION: str = "A FastAPI project"
    APP_VERSION: str = "0.1.0"
    CONTACT_NAME: str = "Your Name"
    CONTACT_EMAIL: str = "your.email@example.com"
    LICENSE_NAME: str = "MIT"
```

### Database Settings
PostgreSQL connection configuration:

```python
class PostgresSettings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:"
            f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
```

### Security Settings
JWT and authentication configuration:

```python
class CryptSettings(BaseSettings):
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v
```

### Redis Settings
Separate Redis instances for different services:

```python
class RedisCacheSettings(BaseSettings):
    REDIS_CACHE_HOST: str = "localhost"
    REDIS_CACHE_PORT: int = 6379

class RedisQueueSettings(BaseSettings):
    REDIS_QUEUE_HOST: str = "localhost"
    REDIS_QUEUE_PORT: int = 6379

class RedisRateLimiterSettings(BaseSettings):
    REDIS_RATE_LIMIT_HOST: str = "localhost"
    REDIS_RATE_LIMIT_PORT: int = 6379
```

### Rate Limiting Settings
Default rate limiting configuration:

```python
class DefaultRateLimitSettings(BaseSettings):
    DEFAULT_RATE_LIMIT_LIMIT: int = 10
    DEFAULT_RATE_LIMIT_PERIOD: int = 3600  # 1 hour
```

### Admin User Settings
First superuser account creation:

```python
class FirstUserSettings(BaseSettings):
    ADMIN_NAME: str = "Admin"
    ADMIN_EMAIL: str
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str

    @field_validator("ADMIN_EMAIL")
    @classmethod
    def validate_admin_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("ADMIN_EMAIL must be a valid email")
        return v
```

## Creating Custom Settings

### Basic Custom Settings

Add your own settings group:

```python
class CustomSettings(BaseSettings):
    CUSTOM_API_KEY: str = ""
    CUSTOM_TIMEOUT: int = 30
    ENABLE_FEATURE_X: bool = False
    MAX_UPLOAD_SIZE: int = 10485760  # 10MB

    @field_validator("MAX_UPLOAD_SIZE")
    @classmethod
    def validate_upload_size(cls, v: int) -> int:
        if v < 1024:  # 1KB minimum
            raise ValueError("MAX_UPLOAD_SIZE must be at least 1KB")
        if v > 104857600:  # 100MB maximum
            raise ValueError("MAX_UPLOAD_SIZE cannot exceed 100MB")
        return v

# Add to main Settings class
class Settings(
    AppSettings,
    PostgresSettings,
    # ... other settings ...
    CustomSettings,  # Add your custom settings
):
    pass
```

### Advanced Custom Settings

Settings with complex validation and computed fields:

```python
class EmailSettings(BaseSettings):
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    EMAIL_FROM: str = ""
    EMAIL_FROM_NAME: str = ""

    @computed_field
    @property
    def EMAIL_ENABLED(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_USERNAME)

    @model_validator(mode="after")
    def validate_email_config(self) -> "EmailSettings":
        if self.SMTP_HOST and not self.EMAIL_FROM:
            raise ValueError("EMAIL_FROM required when SMTP_HOST is set")
        if self.SMTP_USERNAME and not self.SMTP_PASSWORD:
            raise ValueError("SMTP_PASSWORD required when SMTP_USERNAME is set")
        return self
```

### Feature Flag Settings

Organize feature toggles:

```python
class FeatureSettings(BaseSettings):
    # Core features
    ENABLE_CACHING: bool = True
    ENABLE_RATE_LIMITING: bool = True
    ENABLE_BACKGROUND_JOBS: bool = True
    
    # Optional features
    ENABLE_ANALYTICS: bool = False
    ENABLE_EMAIL_NOTIFICATIONS: bool = False
    ENABLE_FILE_UPLOADS: bool = False
    
    # Experimental features
    ENABLE_EXPERIMENTAL_API: bool = False
    ENABLE_BETA_FEATURES: bool = False

    @model_validator(mode="after")
    def validate_feature_dependencies(self) -> "FeatureSettings":
        if self.ENABLE_EMAIL_NOTIFICATIONS and not self.ENABLE_BACKGROUND_JOBS:
            raise ValueError("Email notifications require background jobs")
        return self
```

## Settings Validation

### Field Validation

Validate individual fields:

```python
class DatabaseSettings(BaseSettings):
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 30
    DB_TIMEOUT: int = 30

    @field_validator("DB_POOL_SIZE")
    @classmethod
    def validate_pool_size(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Pool size must be at least 1")
        if v > 100:
            raise ValueError("Pool size should not exceed 100")
        return v

    @field_validator("DB_TIMEOUT")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v < 5:
            raise ValueError("Timeout must be at least 5 seconds")
        return v
```

### Model Validation

Validate across multiple fields:

```python
class SecuritySettings(BaseSettings):
    ENABLE_HTTPS: bool = False
    SSL_CERT_PATH: str = ""
    SSL_KEY_PATH: str = ""
    FORCE_SSL: bool = False

    @model_validator(mode="after")
    def validate_ssl_config(self) -> "SecuritySettings":
        if self.ENABLE_HTTPS:
            if not self.SSL_CERT_PATH:
                raise ValueError("SSL_CERT_PATH required when HTTPS enabled")
            if not self.SSL_KEY_PATH:
                raise ValueError("SSL_KEY_PATH required when HTTPS enabled")
        
        if self.FORCE_SSL and not self.ENABLE_HTTPS:
            raise ValueError("Cannot force SSL without enabling HTTPS")
        
        return self
```

### Environment-Specific Validation

Different validation rules per environment:

```python
class EnvironmentSettings(BaseSettings):
    ENVIRONMENT: str = "local"
    DEBUG: bool = True

    @model_validator(mode="after")
    def validate_environment_config(self) -> "EnvironmentSettings":
        if self.ENVIRONMENT == "production":
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production")
        
        if self.ENVIRONMENT not in ["local", "staging", "production"]:
            raise ValueError("ENVIRONMENT must be local, staging, or production")
        
        return self
```

## Computed Properties

### Dynamic Configuration

Create computed values from other settings:

```python
class StorageSettings(BaseSettings):
    STORAGE_TYPE: str = "local"  # local, s3, gcs
    
    # Local storage
    LOCAL_STORAGE_PATH: str = "./uploads"
    
    # S3 settings
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_BUCKET_NAME: str = ""
    AWS_REGION: str = "us-east-1"

    @computed_field
    @property
    def STORAGE_ENABLED(self) -> bool:
        if self.STORAGE_TYPE == "local":
            return bool(self.LOCAL_STORAGE_PATH)
        elif self.STORAGE_TYPE == "s3":
            return bool(self.AWS_ACCESS_KEY_ID and self.AWS_SECRET_ACCESS_KEY and self.AWS_BUCKET_NAME)
        return False

    @computed_field
    @property
    def STORAGE_CONFIG(self) -> dict:
        if self.STORAGE_TYPE == "local":
            return {"path": self.LOCAL_STORAGE_PATH}
        elif self.STORAGE_TYPE == "s3":
            return {
                "bucket": self.AWS_BUCKET_NAME,
                "region": self.AWS_REGION,
                "credentials": {
                    "access_key": self.AWS_ACCESS_KEY_ID,
                    "secret_key": self.AWS_SECRET_ACCESS_KEY,
                }
            }
        return {}
```

## Organizing Settings

### Service-Based Organization

Group settings by service or domain:

```python
# Authentication service settings
class AuthSettings(BaseSettings):
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE: int = 30
    REFRESH_TOKEN_EXPIRE: int = 7200
    PASSWORD_MIN_LENGTH: int = 8

# Notification service settings  
class NotificationSettings(BaseSettings):
    EMAIL_ENABLED: bool = False
    SMS_ENABLED: bool = False
    PUSH_ENABLED: bool = False
    
    # Email settings
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    
    # SMS settings (example with Twilio)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""

# Main settings
class Settings(
    AppSettings,
    AuthSettings,
    NotificationSettings,
    # ... other settings
):
    pass
```

### Conditional Settings Loading

Load different settings based on environment:

```python
class BaseAppSettings(BaseSettings):
    APP_NAME: str = "FastAPI App"
    DEBUG: bool = False

class DevelopmentSettings(BaseAppSettings):
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    DATABASE_ECHO: bool = True

class ProductionSettings(BaseAppSettings):
    DEBUG: bool = False
    LOG_LEVEL: str = "WARNING"
    DATABASE_ECHO: bool = False

def get_settings() -> BaseAppSettings:
    environment = os.getenv("ENVIRONMENT", "local")
    
    if environment == "production":
        return ProductionSettings()
    else:
        return DevelopmentSettings()

settings = get_settings()
```

## Removing Unused Services

### Minimal Configuration

Remove services you don't need:

```python
# Minimal setup without Redis services
class MinimalSettings(
    AppSettings,
    PostgresSettings,
    CryptSettings,
    FirstUserSettings,
    # Removed: RedisCacheSettings
    # Removed: RedisQueueSettings  
    # Removed: RedisRateLimiterSettings
    EnvironmentSettings,
):
    pass
```

### Service Feature Flags

Use feature flags to conditionally enable services:

```python
class ServiceSettings(BaseSettings):
    ENABLE_REDIS: bool = True
    ENABLE_CELERY: bool = True
    ENABLE_MONITORING: bool = False

class ConditionalSettings(
    AppSettings,
    PostgresSettings,
    CryptSettings,
    ServiceSettings,
):
    # Add Redis settings only if enabled
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        if self.ENABLE_REDIS:
            # Dynamically add Redis settings
            self.__class__ = type(
                "ConditionalSettings",
                (self.__class__, RedisCacheSettings),
                {}
            )
```

## Testing Settings

### Test Configuration

Create separate settings for testing:

```python
class TestSettings(BaseSettings):
    # Override database for testing
    POSTGRES_DB: str = "test_database"
    
    # Disable external services
    ENABLE_REDIS: bool = False
    ENABLE_EMAIL: bool = False
    
    # Speed up tests
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 5
    
    # Test-specific settings
    TEST_USER_EMAIL: str = "test@example.com"
    TEST_USER_PASSWORD: str = "testpassword123"

# Use in tests
@pytest.fixture
def test_settings():
    return TestSettings()
```

### Settings Validation Testing

Test your custom settings:

```python
def test_custom_settings_validation():
    # Test valid configuration
    settings = CustomSettings(
        CUSTOM_API_KEY="test-key",
        CUSTOM_TIMEOUT=60,
        MAX_UPLOAD_SIZE=5242880  # 5MB
    )
    assert settings.CUSTOM_TIMEOUT == 60

    # Test validation error
    with pytest.raises(ValueError, match="MAX_UPLOAD_SIZE cannot exceed 100MB"):
        CustomSettings(MAX_UPLOAD_SIZE=209715200)  # 200MB

def test_settings_computed_fields():
    settings = StorageSettings(
        STORAGE_TYPE="s3",
        AWS_ACCESS_KEY_ID="test-key",
        AWS_SECRET_ACCESS_KEY="test-secret",
        AWS_BUCKET_NAME="test-bucket"
    )
    
    assert settings.STORAGE_ENABLED is True
    assert settings.STORAGE_CONFIG["bucket"] == "test-bucket"
```

## Best Practices

### Organization
- Group related settings in dedicated classes
- Use descriptive names for settings groups
- Keep validation logic close to the settings
- Document complex validation rules

### Security
- Validate sensitive settings like secret keys
- Never set default values for secrets in production
- Use computed fields to derive connection strings
- Separate test and production configurations

### Performance
- Use `@computed_field` for expensive calculations
- Cache settings instances appropriately
- Avoid complex validation in hot paths
- Use model validators for cross-field validation

### Testing
- Create separate test settings classes
- Test all validation rules
- Mock external service settings in tests
- Use dependency injection for settings in tests

The settings system provides type safety, validation, and organization for your application configuration. Start with the built-in settings and extend them as your application grows! 