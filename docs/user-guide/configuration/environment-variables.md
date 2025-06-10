# Configuration Guide

This guide covers all configuration options available in the FastAPI Boilerplate, including environment variables, settings classes, and advanced deployment configurations.

## Configuration Overview

The boilerplate uses a layered configuration approach:

- **Environment Variables** (`.env` file) - Primary configuration method
- **Settings Classes** (`src/app/core/config.py`) - Python-based configuration
- **Docker Configuration** (`docker-compose.yml`) - Container orchestration
- **Database Configuration** (`alembic.ini`) - Database migrations

## Environment Variables Reference

All configuration is managed through environment variables defined in the `.env` file located in the `src/` directory.

### Application Settings

Basic application metadata displayed in API documentation:

```env
# ------------- app settings -------------
APP_NAME="Your App Name"
APP_DESCRIPTION="Your app description here"
APP_VERSION="0.1.0"
CONTACT_NAME="Your Name"
CONTACT_EMAIL="your.email@example.com"
LICENSE_NAME="MIT"
```

**Variables Explained:**

- `APP_NAME`: Displayed in API documentation and responses
- `APP_DESCRIPTION`: Shown in OpenAPI documentation
- `APP_VERSION`: API version for documentation and headers
- `CONTACT_NAME`: Contact information for API documentation
- `CONTACT_EMAIL`: Support email for API users
- `LICENSE_NAME`: License type for the API

### Database Configuration

PostgreSQL database connection settings:

```env
# ------------- database -------------
POSTGRES_USER="your_postgres_user"
POSTGRES_PASSWORD="your_secure_password"
POSTGRES_SERVER="localhost"
POSTGRES_PORT=5432
POSTGRES_DB="your_database_name"
```

**Variables Explained:**

- `POSTGRES_USER`: Database user with appropriate permissions
- `POSTGRES_PASSWORD`: Strong password for database access
- `POSTGRES_SERVER`: Hostname or IP of PostgreSQL server
- `POSTGRES_PORT`: PostgreSQL port (default: 5432)
- `POSTGRES_DB`: Name of the database to connect to

**Environment-Specific Values:**

```env
# Local development
POSTGRES_SERVER="localhost"

# Docker Compose
POSTGRES_SERVER="db"

# Production
POSTGRES_SERVER="your-prod-db-host.com"
```

### Security & Authentication

JWT and password security configuration:

```env
# ------------- crypt -------------
SECRET_KEY="your-super-secret-key-here"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

**Variables Explained:**

- `SECRET_KEY`: Used for JWT token signing (generate with `openssl rand -hex 32`)
- `ALGORITHM`: JWT signing algorithm (HS256 recommended)
- `ACCESS_TOKEN_EXPIRE_MINUTES`: How long access tokens remain valid
- `REFRESH_TOKEN_EXPIRE_DAYS`: How long refresh tokens remain valid

!!! danger "Security Warning"
    Never use default values in production. Generate a strong secret key:
    ```bash
    openssl rand -hex 32
    ```

### Redis Configuration

Redis is used for caching, job queues, and rate limiting:

```env
# ------------- redis cache -------------
REDIS_CACHE_HOST="localhost"  # Use "redis" for Docker Compose
REDIS_CACHE_PORT=6379

# ------------- redis queue -------------
REDIS_QUEUE_HOST="localhost"  # Use "redis" for Docker Compose  
REDIS_QUEUE_PORT=6379

# ------------- redis rate limit -------------
REDIS_RATE_LIMIT_HOST="localhost"  # Use "redis" for Docker Compose
REDIS_RATE_LIMIT_PORT=6379
```

**Best Practices:**

- **Development**: Use the same Redis instance for all services
- **Production**: Use separate Redis instances for better isolation

```env
# Production example with separate instances
REDIS_CACHE_HOST="cache.redis.example.com"
REDIS_QUEUE_HOST="queue.redis.example.com"
REDIS_RATE_LIMIT_HOST="ratelimit.redis.example.com"
```

### Caching Settings

Client-side and server-side caching configuration:

```env
# ------------- redis client-side cache -------------
CLIENT_CACHE_MAX_AGE=30  # seconds
```

**Variables Explained:**

- `CLIENT_CACHE_MAX_AGE`: How long browsers should cache responses

### Rate Limiting

Default rate limiting configuration:

```env
# ------------- default rate limit settings -------------
DEFAULT_RATE_LIMIT_LIMIT=10      # requests per period
DEFAULT_RATE_LIMIT_PERIOD=3600   # period in seconds (1 hour)
```

**Variables Explained:**

- `DEFAULT_RATE_LIMIT_LIMIT`: Number of requests allowed per period
- `DEFAULT_RATE_LIMIT_PERIOD`: Time window in seconds

### Admin User

First superuser account configuration:

```env
# ------------- admin -------------
ADMIN_NAME="Admin User"
ADMIN_EMAIL="admin@example.com"
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="secure_admin_password"
```

**Variables Explained:**

- `ADMIN_NAME`: Display name for the admin user
- `ADMIN_EMAIL`: Email address for the admin account
- `ADMIN_USERNAME`: Username for admin login
- `ADMIN_PASSWORD`: Initial password (change after first login)

### User Tiers

Initial tier configuration:

```env
# ------------- first tier -------------
TIER_NAME="free"
```

**Variables Explained:**

- `TIER_NAME`: Name of the default user tier

### Environment Type

Controls API documentation visibility and behavior:

```env
# ------------- environment -------------
ENVIRONMENT="local"  # local, staging, or production
```

**Environment Types:**

- **local**: Full API docs available publicly at `/docs`
- **staging**: API docs available to superusers only
- **production**: API docs completely disabled

## Docker Compose Configuration

### Basic Setup

Docker Compose automatically loads the `.env` file:

```yaml
# In docker-compose.yml
services:
  web:
    env_file:
      - ./src/.env
```

### Development Overrides

Create `docker-compose.override.yml` for local customizations:

```yaml
version: '3.8'
services:
  web:
    ports:
      - "8001:8000"  # Use different port
    environment:
      - DEBUG=true
    volumes:
      - ./custom-logs:/code/logs
```

### Service Configuration

Understanding each Docker service:

```yaml
services:
  web:          # FastAPI application
  db:           # PostgreSQL database
  redis:        # Redis for caching/queues
  worker:       # ARQ background task worker
  nginx:        # Reverse proxy (optional)
```

## Python Settings Classes

Advanced configuration is handled in `src/app/core/config.py`:

### Settings Composition

The main `Settings` class inherits from multiple setting groups:

```python
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
```

### Adding Custom Settings

Create your own settings group:

```python
class CustomSettings(BaseSettings):
    CUSTOM_API_KEY: str = ""
    CUSTOM_TIMEOUT: int = 30
    ENABLE_FEATURE_X: bool = False

# Add to main Settings class
class Settings(
    AppSettings,
    # ... other settings ...
    CustomSettings,
):
    pass
```

### Opting Out of Services

Remove unused services by excluding their settings:

```python
# Minimal setup without Redis services
class Settings(
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

## Database Configuration

### Alembic Configuration

Database migrations are configured in `src/alembic.ini`:

```ini
[alembic]
script_location = migrations
sqlalchemy.url = postgresql://%(POSTGRES_USER)s:%(POSTGRES_PASSWORD)s@%(POSTGRES_SERVER)s:%(POSTGRES_PORT)s/%(POSTGRES_DB)s
```

### Connection Pooling

SQLAlchemy connection pool settings in `src/app/core/db/database.py`:

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,          # Number of connections to maintain
    max_overflow=30,       # Additional connections allowed
    pool_timeout=30,       # Seconds to wait for connection
    pool_recycle=1800,     # Seconds before connection refresh
)
```

### Database Best Practices

**Connection Pool Sizing:**
- Start with `pool_size=20`, `max_overflow=30`
- Monitor connection usage and adjust based on load
- Use connection pooling monitoring tools

**Migration Strategy:**
- Always backup database before running migrations
- Test migrations on staging environment first
- Use `alembic revision --autogenerate` for model changes

## Security Configuration

### JWT Token Configuration

Customize JWT behavior in `src/app/core/security.py`:

```python
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
```

### CORS Configuration

Configure Cross-Origin Resource Sharing in `src/app/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Specify allowed origins
    allow_credentials=True,
    allow_methods=["GET", "POST"],           # Specify allowed methods
    allow_headers=["*"],
)
```

**Production CORS Settings:**

```python
# Never use wildcard (*) in production
allow_origins=[
    "https://yourapp.com",
    "https://www.yourapp.com"
],
```

### Security Headers

Add security headers middleware:

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response
```

## Logging Configuration

### Basic Logging Setup

Configure logging in `src/app/core/logger.py`:

```python
import logging
from logging.handlers import RotatingFileHandler

# Set log level
LOGGING_LEVEL = logging.INFO

# Configure file rotation
file_handler = RotatingFileHandler(
    'logs/app.log', 
    maxBytes=10485760,  # 10MB
    backupCount=5       # Keep 5 backup files
)
```

### Structured Logging

Use structured logging for better observability:

```python
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)
```

### Log Levels by Environment

```python
# Environment-specific log levels
LOG_LEVELS = {
    "local": logging.DEBUG,
    "staging": logging.INFO,
    "production": logging.WARNING
}

LOGGING_LEVEL = LOG_LEVELS.get(settings.ENVIRONMENT, logging.INFO)
```

## Environment-Specific Configurations

### Development (.env.development)

```env
ENVIRONMENT="local"
POSTGRES_SERVER="localhost"
REDIS_CACHE_HOST="localhost"
SECRET_KEY="dev-secret-key-not-for-production"
ACCESS_TOKEN_EXPIRE_MINUTES=60  # Longer for development
DEBUG=true
```

### Staging (.env.staging)

```env
ENVIRONMENT="staging"
POSTGRES_SERVER="staging-db.example.com"
REDIS_CACHE_HOST="staging-redis.example.com"
SECRET_KEY="staging-secret-key-different-from-prod"
ACCESS_TOKEN_EXPIRE_MINUTES=30
DEBUG=false
```

### Production (.env.production)

```env
ENVIRONMENT="production"
POSTGRES_SERVER="prod-db.example.com"
REDIS_CACHE_HOST="prod-redis.example.com"
SECRET_KEY="ultra-secure-production-key-generated-with-openssl"
ACCESS_TOKEN_EXPIRE_MINUTES=15
DEBUG=false
REDIS_CACHE_PORT=6380  # Custom port for security
POSTGRES_PORT=5433     # Custom port for security
```

## Advanced Configuration

### Custom Middleware

Add custom middleware in `src/app/core/setup.py`:

```python
def create_application(router, settings, **kwargs):
    app = FastAPI(...)
    
    # Add custom middleware
    app.add_middleware(CustomMiddleware, setting=value)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    
    return app
```

### Feature Toggles

Implement feature flags:

```python
class FeatureSettings(BaseSettings):
    ENABLE_ADVANCED_CACHING: bool = False
    ENABLE_ANALYTICS: bool = True  
    ENABLE_EXPERIMENTAL_FEATURES: bool = False
    ENABLE_API_VERSIONING: bool = True

# Use in endpoints
if settings.ENABLE_ADVANCED_CACHING:
    # Advanced caching logic
    pass
```

### Health Checks

Configure health check endpoints:

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": await check_database_health(),
        "redis": await check_redis_health(),
        "version": settings.APP_VERSION
    }
```

## Configuration Validation

### Environment Validation

Add validation to prevent misconfiguration:

```python
def validate_settings():
    if not settings.SECRET_KEY:
        raise ValueError("SECRET_KEY must be set")
    
    if settings.ENVIRONMENT == "production":
        if settings.SECRET_KEY == "dev-secret-key":
            raise ValueError("Production must use secure SECRET_KEY")
        
        if settings.DEBUG:
            raise ValueError("DEBUG must be False in production")
```

### Runtime Checks

Add validation to application startup:

```python
@app.on_event("startup")
async def startup_event():
    validate_settings()
    await check_database_connection()
    await check_redis_connection()
    logger.info(f"Application started in {settings.ENVIRONMENT} mode")
```

## Configuration Troubleshooting

### Common Issues

**Environment Variables Not Loading:**
```bash
# Check file location and permissions
ls -la src/.env

# Check file format (no spaces around =)
cat src/.env | grep "=" | head -5

# Verify environment loading in Python
python -c "from src.app.core.config import settings; print(settings.APP_NAME)"
```

**Database Connection Failed:**
```bash
# Test connection manually
psql -h localhost -U postgres -d myapp

# Check if PostgreSQL is running
systemctl status postgresql
# or on macOS
brew services list | grep postgresql
```

**Redis Connection Failed:**
```bash
# Test Redis connection
redis-cli -h localhost -p 6379 ping

# Check Redis status
systemctl status redis
# or on macOS  
brew services list | grep redis
```

### Configuration Testing

Test your configuration with a simple script:

```python
# test_config.py
import asyncio
from src.app.core.config import settings
from src.app.core.db.database import async_get_db

async def test_config():
    print(f"App: {settings.APP_NAME}")
    print(f"Environment: {settings.ENVIRONMENT}")
    
    # Test database
    try:
        db = await anext(async_get_db())
        print("✓ Database connection successful")
        await db.close()
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
    
    # Test Redis (if enabled)
    try:
        from src.app.core.utils.cache import redis_client
        await redis_client.ping()
        print("✓ Redis connection successful")
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_config())
```

Run with:
```bash
uv run python test_config.py
``` 