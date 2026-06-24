# Configuration

Learn how to configure your FastAPI Boilerplate application for different environments. Configuration is driven by environment variables and validated by Python settings classes.

## What You'll Learn

- **[Environment Variables](environment-variables.md)** - Configure through `.env` files
- **[Settings Classes](settings-classes.md)** - Python-based configuration management
- **[Docker Setup](docker-setup.md)** - Container and service configuration
- **[Environment-Specific](environment-specific.md)** - Development, staging, and production configs

## Quick Start

```bash
cd backend
cp .env.example .env
$EDITOR .env
```

Essential variables:

```env
# Application
APP_NAME=My FastAPI App
SECRET_KEY=your-super-secret-key-here

# Database
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=your_database

# Admin Account (used by setup_initial_data)
ADMIN_NAME=Admin User
ADMIN_EMAIL=admin@example.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=secure_password
```

## Configuration Architecture

```
Environment Variables (.env file)
         ↓
Settings Classes (Pydantic BaseSettings)
         ↓
Application Code (via get_settings())
```

### Layer 1: Environment Variables

Primary configuration through `backend/.env`:

```env
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
CACHE_REDIS_HOST=localhost
SECRET_KEY=your-secret-key
```

### Layer 2: Settings Classes

Pydantic `BaseSettings` classes in `src/infrastructure/config/settings.py` validate and structure config:

```python
class DatabaseSettings(BaseSettings):
    POSTGRES_USER: str = config("POSTGRES_USER", default="postgres")
    POSTGRES_PASSWORD: str = config("POSTGRES_PASSWORD", default="postgres")
    POSTGRES_SERVER: str = config("POSTGRES_SERVER", default="localhost")
    POSTGRES_PORT: int = config("POSTGRES_PORT", default=5432)
    POSTGRES_DB: str = config("POSTGRES_DB", default="postgres")
```

A single composite `Settings` class combines them all.

### Layer 3: Application Use

Pull settings anywhere in the app via `get_settings()`:

```python
from src.infrastructure.config.settings import get_settings

settings = get_settings()
print(settings.DATABASE_URL)
```

## Key Configuration Areas

### Application Settings

```env
APP_NAME=Your App Name
VERSION=1.0.0
ENVIRONMENT=development  # development | staging | production | local
DEBUG=false
```

### Database

```env
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_SERVER=localhost   # use "db" with Docker Compose
POSTGRES_PORT=5432
POSTGRES_DB=your_database
CREATE_TABLES_ON_STARTUP=true
```

### Security & Sessions

```env
SECRET_KEY=your-super-secret-key-here

SESSION_TIMEOUT_MINUTES=30
SESSION_SECURE_COOKIES=true
SESSION_BACKEND=redis           # redis | memory
CSRF_ENABLED=true
TRUSTED_PROXY_HOPS=0            # trusted reverse proxies in front of the app
```

Login lockout is applied internally by `crudauth` (escalating per-IP / per-identifier; returns `429` with `Retry-After`) — it is not configured via env vars.

### Cache (Redis or Memcached)

```env
CACHE_ENABLED=true
CACHE_BACKEND=redis           # or "memcached"
CACHE_REDIS_HOST=localhost    # use "redis" with Docker Compose
CACHE_REDIS_PORT=6379
CACHE_REDIS_DB=0
DEFAULT_CACHE_EXPIRATION=3600
```

### Background Tasks (Taskiq)

```env
TASKIQ_ENABLED=true
TASKIQ_BROKER_TYPE=redis      # or "rabbitmq"
TASKIQ_REDIS_HOST=localhost   # use "redis" with Docker Compose
TASKIQ_REDIS_PORT=6379
TASKIQ_REDIS_DB=3
```

### Rate Limiting

```env
RATE_LIMITER_ENABLED=true
RATE_LIMITER_BACKEND=redis
RATE_LIMITER_REDIS_HOST=localhost
RATE_LIMITER_REDIS_DB=1
DEFAULT_RATE_LIMIT_LIMIT=100
DEFAULT_RATE_LIMIT_PERIOD=60
```

### Admin User (Initial Setup)

Read by `python -m scripts.setup_initial_data` on first run:

```env
ADMIN_NAME=Admin User
ADMIN_EMAIL=admin@example.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=secure_password
```

## Environment-Specific Configurations

### Development

```env
ENVIRONMENT=development
DEBUG=true
POSTGRES_SERVER=localhost
CACHE_REDIS_HOST=localhost
TASKIQ_REDIS_HOST=localhost
RATE_LIMITER_REDIS_HOST=localhost
```

### Staging

```env
ENVIRONMENT=staging
DEBUG=false
POSTGRES_SERVER=staging-db.example.com
CACHE_REDIS_HOST=staging-redis.example.com
SESSION_SECURE_COOKIES=true
```

### Production

```env
ENVIRONMENT=production
DEBUG=false
POSTGRES_SERVER=prod-db.example.com
CACHE_REDIS_HOST=prod-redis.example.com
PRODUCTION_SECURITY_VALIDATION_ENABLED=true
PRODUCTION_SECURITY_STRICT_MODE=true
ENABLE_DOCS_IN_PRODUCTION=false
```

## Docker Configuration

Docker Compose loads variables from `.env` automatically. With Compose, services reach each other by service name:

```env
POSTGRES_SERVER=db
CACHE_REDIS_HOST=redis
RATE_LIMITER_REDIS_HOST=redis
TASKIQ_REDIS_HOST=redis
```

### Service Overview

```yaml
services:
  web:    # FastAPI application
  db:     # PostgreSQL
  redis:  # Cache, rate limiting, sessions, taskiq broker
```

To run a Taskiq worker, add a worker service to your Compose file with the command `taskiq worker infrastructure.taskiq.worker:default_broker`.

## Common Configuration Patterns

### Feature Toggles

The boilerplate already exposes toggles like `CACHE_ENABLED`, `RATE_LIMITER_ENABLED`, `TASKIQ_ENABLED`, `ADMIN_ENABLED`, and `CSRF_ENABLED`. You can add your own in a settings class:

```python
class FeatureSettings(BaseSettings):
    ENABLE_ANALYTICS: bool = config("ENABLE_ANALYTICS", default=False, cast=bool)
```

Then use it:

```python
from src.infrastructure.config.settings import get_settings

if get_settings().ENABLE_ANALYTICS:
    track_event(...)
```

### Environment Detection

```python
from src.infrastructure.config.settings import EnvironmentOption, get_settings

if get_settings().ENVIRONMENT == EnvironmentOption.PRODUCTION:
    ...
```

### Generate Secret Key

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Best Practices

### Security
- Never commit `.env` to version control
- Use a unique strong `SECRET_KEY` per environment
- Disable debug mode in production
- Set `ENVIRONMENT=production` to enable the security validator
- Restrict `CORS_ORIGINS` to specific domains

### Performance
- Tune `POSTGRES_POOL_SIZE` and `POSTGRES_MAX_OVERFLOW` for your workload
- Use separate Redis databases for cache (`CACHE_REDIS_DB=0`), rate limiting (`RATE_LIMITER_REDIS_DB=1`), and taskiq (`TASKIQ_REDIS_DB=3`)
- Set sensible `SESSION_TIMEOUT_MINUTES` and `MAX_SESSIONS_PER_USER`

### Maintenance
- Document custom environment variables in `.env.example`
- Add validation in settings classes (Pydantic types catch most issues)
- Test configurations in staging before production

## Getting Started

1. **[Environment Variables](environment-variables.md)** - Complete reference of every variable
2. **[Settings Classes](settings-classes.md)** - How config is organized in Python
3. **[Docker Setup](docker-setup.md)** - Compose files and overrides
4. **[Environment-Specific](environment-specific.md)** - Per-environment best practices

The boilerplate ships with sensible defaults — only override what you need.
