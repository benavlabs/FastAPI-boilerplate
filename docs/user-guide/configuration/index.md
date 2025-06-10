# Configuration

Learn how to configure your FastAPI Boilerplate application for different environments and use cases. Everything is configured through environment variables and Python settings classes.

## What You'll Learn

- **[Environment Variables](environment-variables.md)** - Configure through `.env` files
- **[Settings Classes](settings-classes.md)** - Python-based configuration management
- **[Docker Setup](docker-setup.md)** - Container and service configuration
- **[Environment-Specific](environment-specific.md)** - Development, staging, and production configs

## Quick Start

The boilerplate uses environment variables as the primary configuration method:

```bash
# Copy the example file
cp src/.env.example src/.env

# Edit with your values
nano src/.env
```

Essential variables to set:

```env
# Application
APP_NAME="My FastAPI App"
SECRET_KEY="your-super-secret-key-here"

# Database
POSTGRES_USER="your_user"
POSTGRES_PASSWORD="your_password"
POSTGRES_DB="your_database"

# Admin Account
ADMIN_EMAIL="admin@example.com"
ADMIN_PASSWORD="secure_password"
```

## Configuration Architecture

The configuration system has three layers:

```
Environment Variables (.env files)
         ↓
Settings Classes (Python validation)
         ↓
Application Configuration (Runtime)
```

### Layer 1: Environment Variables
Primary configuration through `.env` files:
```env
POSTGRES_USER="myuser"
POSTGRES_PASSWORD="mypassword"
REDIS_CACHE_HOST="localhost"
SECRET_KEY="your-secret-key"
```

### Layer 2: Settings Classes
Python classes that validate and structure configuration:
```python
class PostgresSettings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = Field(min_length=8)
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str
```

### Layer 3: Application Use
Configuration injected throughout the application:
```python
from app.core.config import settings

# Use anywhere in your code
DATABASE_URL = f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
```

## Key Configuration Areas

### Security Settings
```env
SECRET_KEY="your-super-secret-key-here"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

### Database Configuration
```env
POSTGRES_USER="your_user"
POSTGRES_PASSWORD="your_password"
POSTGRES_SERVER="localhost"
POSTGRES_PORT=5432
POSTGRES_DB="your_database"
```

### Redis Services
```env
# Cache
REDIS_CACHE_HOST="localhost"
REDIS_CACHE_PORT=6379

# Background jobs
REDIS_QUEUE_HOST="localhost"
REDIS_QUEUE_PORT=6379

# Rate limiting  
REDIS_RATE_LIMIT_HOST="localhost"
REDIS_RATE_LIMIT_PORT=6379
```

### Application Settings
```env
APP_NAME="Your App Name"
APP_VERSION="1.0.0"
ENVIRONMENT="local"  # local, staging, production
DEBUG=true
```

### Rate Limiting
```env
DEFAULT_RATE_LIMIT_LIMIT=100
DEFAULT_RATE_LIMIT_PERIOD=3600  # 1 hour in seconds
```

### Admin User
```env
ADMIN_NAME="Admin User"
ADMIN_EMAIL="admin@example.com"
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="secure_password"
```

## Environment-Specific Configurations

### Development
```env
ENVIRONMENT="local"
DEBUG=true
POSTGRES_SERVER="localhost"
REDIS_CACHE_HOST="localhost"
ACCESS_TOKEN_EXPIRE_MINUTES=60  # Longer for development
```

### Staging
```env
ENVIRONMENT="staging"
DEBUG=false
POSTGRES_SERVER="staging-db.example.com"
REDIS_CACHE_HOST="staging-redis.example.com"
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Production
```env
ENVIRONMENT="production"
DEBUG=false
POSTGRES_SERVER="prod-db.example.com"
REDIS_CACHE_HOST="prod-redis.example.com"
ACCESS_TOKEN_EXPIRE_MINUTES=15
# Use custom ports for security
POSTGRES_PORT=5433
REDIS_CACHE_PORT=6380
```

## Docker Configuration

### Basic Setup
Docker Compose automatically loads your `.env` file:

```yaml
services:
  web:
    env_file:
      - ./src/.env
    environment:
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
```

### Service Overview
```yaml
services:
  web:          # FastAPI application
  db:           # PostgreSQL database  
  redis:        # Redis for caching/queues
  worker:       # Background task worker
```

## Common Configuration Patterns

### Feature Flags
```python
# In settings class
class FeatureSettings(BaseSettings):
    ENABLE_CACHING: bool = True
    ENABLE_ANALYTICS: bool = False
    ENABLE_BACKGROUND_JOBS: bool = True

# Use in code
if settings.ENABLE_CACHING:
    cache_result = await get_from_cache(key)
```

### Environment Detection
```python
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    if settings.ENVIRONMENT == "production":
        raise HTTPException(404, "Documentation not available")
    return get_swagger_ui_html(openapi_url="/openapi.json")
```

### Health Checks
```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": settings.APP_VERSION,
        "database": await check_database_health(),
        "redis": await check_redis_health()
    }
```

## Quick Configuration Tasks

### Generate Secret Key
```bash
# Generate a secure secret key
openssl rand -hex 32
```

### Test Configuration
```python
# test_config.py
from app.core.config import settings

print(f"App: {settings.APP_NAME}")
print(f"Environment: {settings.ENVIRONMENT}")
print(f"Database: {settings.POSTGRES_DB}")
```

### Environment File Templates
```bash
# Development
cp src/.env.example src/.env.development

# Staging  
cp src/.env.example src/.env.staging

# Production
cp src/.env.example src/.env.production
```

## Best Practices

### Security
- Never commit `.env` files to version control
- Use different secret keys for each environment
- Disable debug mode in production
- Use secure passwords and keys

### Performance
- Configure appropriate connection pool sizes
- Set reasonable token expiration times
- Use Redis for caching in production
- Configure proper rate limits

### Maintenance
- Document all custom environment variables
- Use validation in settings classes
- Test configurations in staging first
- Monitor configuration changes

### Testing
- Use separate test environment variables
- Mock external services in tests
- Validate configuration on startup
- Test with different environment combinations

## Getting Started

Follow this path to configure your application:

### 1. **[Environment Variables](environment-variables.md)** - Start here
Learn about all available environment variables, their purposes, and recommended values for different environments.

### 2. **[Settings Classes](settings-classes.md)** - Validation layer
Understand how Python settings classes validate and structure your configuration with type hints and validation rules.

### 3. **[Docker Setup](docker-setup.md)** - Container configuration
Configure Docker Compose services, networking, and environment-specific overrides.

### 4. **[Environment-Specific](environment-specific.md)** - Deployment configs
Set up configuration for development, staging, and production environments with best practices.

## What's Next

Each guide provides practical examples and copy-paste configurations:

1. **[Environment Variables](environment-variables.md)** - Complete reference and examples
2. **[Settings Classes](settings-classes.md)** - Custom validation and organization
3. **[Docker Setup](docker-setup.md)** - Service configuration and overrides
4. **[Environment-Specific](environment-specific.md)** - Production-ready configurations

The boilerplate provides sensible defaults - just customize what you need! 