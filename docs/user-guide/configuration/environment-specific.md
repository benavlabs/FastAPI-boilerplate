# Environment-Specific Configuration

Learn how to configure your FastAPI application for different environments (development, staging, production) with appropriate security, performance, and monitoring settings.

## Environment Types

The boilerplate supports three environment types:

- **`local`** - Development environment with full debugging
- **`staging`** - Pre-production testing environment  
- **`production`** - Production environment with security hardening

Set the environment type with:

```env
ENVIRONMENT="local"  # or "staging" or "production"
```

## Development Environment

### Local Development Settings

Create `src/.env.development`:

```env
# ------------- environment -------------
ENVIRONMENT="local"
DEBUG=true

# ------------- app settings -------------
APP_NAME="MyApp (Development)"
APP_VERSION="0.1.0-dev"

# ------------- database -------------
POSTGRES_USER="dev_user"
POSTGRES_PASSWORD="dev_password"
POSTGRES_SERVER="localhost"
POSTGRES_PORT=5432
POSTGRES_DB="myapp_dev"

# ------------- crypt -------------
SECRET_KEY="dev-secret-key-not-for-production-use"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=60  # Longer for development
REFRESH_TOKEN_EXPIRE_DAYS=30     # Longer for development

# ------------- redis -------------
REDIS_CACHE_HOST="localhost"
REDIS_CACHE_PORT=6379
REDIS_QUEUE_HOST="localhost"
REDIS_QUEUE_PORT=6379
REDIS_RATE_LIMIT_HOST="localhost"
REDIS_RATE_LIMIT_PORT=6379

# ------------- caching -------------
CLIENT_CACHE_MAX_AGE=0  # Disable caching for development

# ------------- rate limiting -------------
DEFAULT_RATE_LIMIT_LIMIT=1000   # Higher limits for development
DEFAULT_RATE_LIMIT_PERIOD=3600

# ------------- admin -------------
ADMIN_NAME="Dev Admin"
ADMIN_EMAIL="admin@localhost"
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="admin123"

# ------------- tier -------------
TIER_NAME="dev_tier"

# ------------- logging -------------
DATABASE_ECHO=true  # Log all SQL queries
```

### Development Features

```python
# Development-specific features
if settings.ENVIRONMENT == "local":
    # Enable detailed error pages
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins in development
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Enable API documentation
    app.openapi_url = "/openapi.json"
    app.docs_url = "/docs"
    app.redoc_url = "/redoc"
```

### Docker Development Override

`docker-compose.override.yml`:

```yaml
version: '3.8'

services:
  web:
    environment:
      - ENVIRONMENT=local
      - DEBUG=true
      - DATABASE_ECHO=true
    volumes:
      - ./src:/code/src:cached
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"

  db:
    environment:
      - POSTGRES_DB=myapp_dev
    ports:
      - "5432:5432"

  redis:
    ports:
      - "6379:6379"

  # Development tools
  adminer:
    image: adminer
    ports:
      - "8080:8080"
    depends_on:
      - db
```

## Staging Environment

### Staging Settings

Create `src/.env.staging`:

```env
# ------------- environment -------------
ENVIRONMENT="staging"
DEBUG=false

# ------------- app settings -------------
APP_NAME="MyApp (Staging)"
APP_VERSION="0.1.0-staging"

# ------------- database -------------
POSTGRES_USER="staging_user"
POSTGRES_PASSWORD="complex_staging_password_123!"
POSTGRES_SERVER="staging-db.example.com"
POSTGRES_PORT=5432
POSTGRES_DB="myapp_staging"

# ------------- crypt -------------
SECRET_KEY="staging-secret-key-different-from-production"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# ------------- redis -------------
REDIS_CACHE_HOST="staging-redis.example.com"
REDIS_CACHE_PORT=6379
REDIS_QUEUE_HOST="staging-redis.example.com"
REDIS_QUEUE_PORT=6379
REDIS_RATE_LIMIT_HOST="staging-redis.example.com"
REDIS_RATE_LIMIT_PORT=6379

# ------------- caching -------------
CLIENT_CACHE_MAX_AGE=300  # 5 minutes

# ------------- rate limiting -------------
DEFAULT_RATE_LIMIT_LIMIT=100
DEFAULT_RATE_LIMIT_PERIOD=3600

# ------------- admin -------------
ADMIN_NAME="Staging Admin"
ADMIN_EMAIL="admin@staging.example.com"
ADMIN_USERNAME="staging_admin"
ADMIN_PASSWORD="secure_staging_password_456!"

# ------------- tier -------------
TIER_NAME="staging_tier"

# ------------- logging -------------
DATABASE_ECHO=false
```

### Staging Features

```python
# Staging-specific features
if settings.ENVIRONMENT == "staging":
    # Restricted CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://staging.example.com"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    
    # API docs available to superusers only
    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui(current_user: User = Depends(get_current_superuser)):
        return get_swagger_ui_html(openapi_url="/openapi.json")
```

### Docker Staging Configuration

`docker-compose.staging.yml`:

```yaml
version: '3.8'

services:
  web:
    environment:
      - ENVIRONMENT=staging
      - DEBUG=false
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
    restart: always

  db:
    environment:
      - POSTGRES_DB=myapp_staging
    volumes:
      - postgres_staging_data:/var/lib/postgresql/data
    restart: always

  redis:
    restart: always

  worker:
    deploy:
      replicas: 2
    restart: always

volumes:
  postgres_staging_data:
```

## Production Environment

### Production Settings

Create `src/.env.production`:

```env
# ------------- environment -------------
ENVIRONMENT="production"
DEBUG=false

# ------------- app settings -------------
APP_NAME="MyApp"
APP_VERSION="1.0.0"
CONTACT_NAME="Support Team"
CONTACT_EMAIL="support@example.com"

# ------------- database -------------
POSTGRES_USER="prod_user"
POSTGRES_PASSWORD="ultra_secure_production_password_789!"
POSTGRES_SERVER="prod-db.example.com"
POSTGRES_PORT=5433  # Custom port for security
POSTGRES_DB="myapp_production"

# ------------- crypt -------------
SECRET_KEY="ultra-secure-production-key-generated-with-openssl-rand-hex-32"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=15  # Shorter for security
REFRESH_TOKEN_EXPIRE_DAYS=3     # Shorter for security

# ------------- redis -------------
REDIS_CACHE_HOST="prod-redis.example.com"
REDIS_CACHE_PORT=6380  # Custom port for security
REDIS_QUEUE_HOST="prod-redis.example.com"
REDIS_QUEUE_PORT=6380
REDIS_RATE_LIMIT_HOST="prod-redis.example.com"
REDIS_RATE_LIMIT_PORT=6380

# ------------- caching -------------
CLIENT_CACHE_MAX_AGE=3600  # 1 hour

# ------------- rate limiting -------------
DEFAULT_RATE_LIMIT_LIMIT=100
DEFAULT_RATE_LIMIT_PERIOD=3600

# ------------- admin -------------
ADMIN_NAME="System Administrator"
ADMIN_EMAIL="admin@example.com"
ADMIN_USERNAME="sysadmin"
ADMIN_PASSWORD="extremely_secure_admin_password_with_symbols_#$%!"

# ------------- tier -------------
TIER_NAME="production_tier"

# ------------- logging -------------
DATABASE_ECHO=false
```

### Production Security Features

```python
# Production-specific features
if settings.ENVIRONMENT == "production":
    # Strict CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://example.com", "https://www.example.com"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    
    # Disable API documentation
    app.openapi_url = None
    app.docs_url = None
    app.redoc_url = None
    
    # Add security headers
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
```

### Docker Production Configuration

`docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  web:
    environment:
      - ENVIRONMENT=production
      - DEBUG=false
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 2G
          cpus: '1'
        reservations:
          memory: 1G
          cpus: '0.5'
    restart: always
    ports: []  # No direct exposure

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
      - ./nginx/htpasswd:/etc/nginx/htpasswd
    depends_on:
      - web
    restart: always

  db:
    environment:
      - POSTGRES_DB=myapp_production
    volumes:
      - postgres_prod_data:/var/lib/postgresql/data
    ports: []  # No external access
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
    restart: always

  redis:
    volumes:
      - redis_prod_data:/data
    ports: []  # No external access
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
    restart: always

  worker:
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
    restart: always

volumes:
  postgres_prod_data:
  redis_prod_data:
```

## Environment Detection

### Runtime Environment Checks

```python
# src/app/core/config.py
class Settings(BaseSettings):
    @computed_field
    @property
    def IS_DEVELOPMENT(self) -> bool:
        return self.ENVIRONMENT == "local"
    
    @computed_field
    @property
    def IS_PRODUCTION(self) -> bool:
        return self.ENVIRONMENT == "production"
    
    @computed_field
    @property
    def IS_STAGING(self) -> bool:
        return self.ENVIRONMENT == "staging"

# Use in application
if settings.IS_DEVELOPMENT:
    # Development-only code
    pass

if settings.IS_PRODUCTION:
    # Production-only code
    pass
```

### Environment-Specific Validation

```python
@model_validator(mode="after")
def validate_environment_config(self) -> "Settings":
    if self.ENVIRONMENT == "production":
        # Production validation
        if self.DEBUG:
            raise ValueError("DEBUG must be False in production")
        if len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in production")
        if "dev" in self.SECRET_KEY.lower():
            raise ValueError("Production SECRET_KEY cannot contain 'dev'")
    
    if self.ENVIRONMENT == "local":
        # Development warnings
        if not self.DEBUG:
            logger.warning("DEBUG is False in development environment")
    
    return self
```

## Configuration Management

### Environment File Templates

Create template files for each environment:

```bash
# Create environment templates
cp src/.env.example src/.env.development
cp src/.env.example src/.env.staging
cp src/.env.example src/.env.production

# Use environment-specific files
ln -sf .env.development src/.env  # For development
ln -sf .env.staging src/.env      # For staging
ln -sf .env.production src/.env   # For production
```

### Configuration Validation

```python
# src/scripts/validate_config.py
import asyncio
from src.app.core.config import settings
from src.app.core.db.database import async_get_db

async def validate_configuration():
    """Validate configuration for current environment."""
    print(f"Validating configuration for {settings.ENVIRONMENT} environment...")
    
    # Basic settings validation
    assert settings.APP_NAME, "APP_NAME is required"
    assert settings.SECRET_KEY, "SECRET_KEY is required"
    assert len(settings.SECRET_KEY) >= 32, "SECRET_KEY must be at least 32 characters"
    
    # Environment-specific validation
    if settings.ENVIRONMENT == "production":
        assert not settings.DEBUG, "DEBUG must be False in production"
        assert "dev" not in settings.SECRET_KEY.lower(), "Production SECRET_KEY invalid"
        assert settings.POSTGRES_PORT != 5432, "Use custom PostgreSQL port in production"
    
    # Test database connection
    try:
        db = await anext(async_get_db())
        print("✓ Database connection successful")
        await db.close()
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False
    
    print("✓ Configuration validation passed")
    return True

if __name__ == "__main__":
    asyncio.run(validate_configuration())
```

### Environment Switching

```bash
#!/bin/bash
# scripts/switch_env.sh

ENV=$1

if [ -z "$ENV" ]; then
    echo "Usage: $0 <development|staging|production>"
    exit 1
fi

case $ENV in
    development)
        ln -sf .env.development src/.env
        echo "Switched to development environment"
        ;;
    staging)
        ln -sf .env.staging src/.env
        echo "Switched to staging environment"
        ;;
    production)
        ln -sf .env.production src/.env
        echo "Switched to production environment"
        echo "WARNING: Make sure to review all settings before deployment!"
        ;;
    *)
        echo "Invalid environment: $ENV"
        echo "Valid options: development, staging, production"
        exit 1
        ;;
esac

# Validate configuration
python -c "from src.app.core.config import settings; print(f'Current environment: {settings.ENVIRONMENT}')"
```

## Security Best Practices

### Environment-Specific Security

```python
# Different security levels per environment
SECURITY_CONFIGS = {
    "local": {
        "token_expire_minutes": 60,
        "enable_cors_origins": ["*"],
        "enable_docs": True,
        "log_level": "DEBUG",
    },
    "staging": {
        "token_expire_minutes": 30,
        "enable_cors_origins": ["https://staging.example.com"],
        "enable_docs": True,  # For testing
        "log_level": "INFO",
    },
    "production": {
        "token_expire_minutes": 15,
        "enable_cors_origins": ["https://example.com"],
        "enable_docs": False,
        "log_level": "WARNING",
    }
}

config = SECURITY_CONFIGS[settings.ENVIRONMENT]
```

### Secrets Management

```bash
# Use secrets management in production
# Instead of plain text environment variables
POSTGRES_PASSWORD_FILE="/run/secrets/postgres_password"
SECRET_KEY_FILE="/run/secrets/jwt_secret"

# Docker secrets
services:
  web:
    secrets:
      - postgres_password
      - jwt_secret
    environment:
      - POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
      - SECRET_KEY_FILE=/run/secrets/jwt_secret

secrets:
  postgres_password:
    external: true
  jwt_secret:
    external: true
```

## Monitoring and Logging

### Environment-Specific Logging

```python
LOGGING_CONFIG = {
    "local": {
        "level": "DEBUG",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "handlers": ["console"],
    },
    "staging": {
        "level": "INFO", 
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "handlers": ["console", "file"],
    },
    "production": {
        "level": "WARNING",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
        "handlers": ["file", "syslog"],
    }
}
```

### Health Checks by Environment

```python
@app.get("/health")
async def health_check():
    health_info = {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": settings.APP_VERSION,
    }
    
    # Add detailed info in non-production
    if not settings.IS_PRODUCTION:
        health_info.update({
            "database": await check_database_health(),
            "redis": await check_redis_health(),
            "worker_queue": await check_worker_health(),
        })
    
    return health_info
```

## Best Practices

### Security
- Use different secret keys for each environment
- Disable debug mode in staging and production
- Use custom ports in production
- Implement proper CORS policies
- Remove API documentation in production

### Performance
- Configure appropriate resource limits per environment
- Use caching in staging and production
- Set shorter token expiration in production
- Use connection pooling in production

### Configuration
- Keep environment files in version control (except production)
- Use validation to prevent misconfiguration
- Document all environment-specific settings
- Test configuration changes in staging first

### Monitoring
- Use appropriate log levels per environment
- Monitor different metrics in each environment
- Set up alerts for production only
- Use health checks for all environments

Environment-specific configuration ensures your application runs securely and efficiently in each deployment stage. Start with development settings and progressively harden for production! 