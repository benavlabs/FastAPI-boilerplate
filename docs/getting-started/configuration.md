# Configuration

This guide covers the essential configuration steps to get your FastAPI application running quickly.

## Quick Setup

The fastest way to get started is to copy the example environment file and modify just a few values:

```bash
cp src/.env.example src/.env
```

## Essential Configuration

Open `src/.env` and set these required values:

### Application Settings

```env
# App Settings  
APP_NAME="Your app name here"
APP_DESCRIPTION="Your app description here"
APP_VERSION="0.1"
CONTACT_NAME="Your name"
CONTACT_EMAIL="Your email"
LICENSE_NAME="The license you picked"
```

### Database Connection

```env
# Database
POSTGRES_USER="your_postgres_user"
POSTGRES_PASSWORD="your_password"
POSTGRES_SERVER="localhost"  # Use "db" for Docker Compose
POSTGRES_PORT=5432           # Use 5432 for Docker Compose
POSTGRES_DB="your_database_name"
```

### PGAdmin (Optional)

For database administration:

```env
# PGAdmin
PGADMIN_DEFAULT_EMAIL="your_email_address"
PGADMIN_DEFAULT_PASSWORD="your_password"
PGADMIN_LISTEN_PORT=80
```

**To connect to database in PGAdmin:**
1. Login with `PGADMIN_DEFAULT_EMAIL` and `PGADMIN_DEFAULT_PASSWORD`
2. Click "Add Server"
3. Use these connection settings:
   - **Hostname/address**: `db` (if using containers) or `localhost`
   - **Port**: Value from `POSTGRES_PORT`
   - **Database**: `postgres` (leave as default)
   - **Username**: Value from `POSTGRES_USER`
   - **Password**: Value from `POSTGRES_PASSWORD`

### Security

Generate a secret key and set it:

```bash
# Generate a secure secret key
openssl rand -hex 32
```

```env
# Cryptography
SECRET_KEY="your-generated-secret-key-here"  # Result of openssl rand -hex 32
ALGORITHM="HS256"                            # Default: HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30               # Default: 30
REFRESH_TOKEN_EXPIRE_DAYS=7                  # Default: 7
```

### First Admin User

```env
# Admin User
ADMIN_NAME="your_name"
ADMIN_EMAIL="your_email"
ADMIN_USERNAME="your_username"
ADMIN_PASSWORD="your_password"
```

### Redis Configuration

```env
# Redis Cache
REDIS_CACHE_HOST="localhost"     # Use "redis" for Docker Compose
REDIS_CACHE_PORT=6379

# Client-side Cache
CLIENT_CACHE_MAX_AGE=30          # Default: 30 seconds

# Redis Job Queue
REDIS_QUEUE_HOST="localhost"     # Use "redis" for Docker Compose  
REDIS_QUEUE_PORT=6379

# Redis Rate Limiting
REDIS_RATE_LIMIT_HOST="localhost"  # Use "redis" for Docker Compose
REDIS_RATE_LIMIT_PORT=6379
```

!!! warning "Redis in Production"
    You may use the same Redis instance for caching and queues while developing, but use separate containers in production.

### Rate Limiting Defaults

```env
# Default Rate Limits
DEFAULT_RATE_LIMIT_LIMIT=10      # Default: 10 requests
DEFAULT_RATE_LIMIT_PERIOD=3600   # Default: 3600 seconds (1 hour)
```

### First Tier

```env
# Default Tier
TIER_NAME="free"
```

## Environment Types

Set your environment type:

```env
ENVIRONMENT="local"  # local, staging, or production
```

- **local**: API docs available at `/docs`, `/redoc`, and `/openapi.json`
- **staging**: API docs available to superusers only
- **production**: API docs completely disabled

## Docker Compose Settings

If using Docker Compose, use these values instead:

```env
# Docker Compose values
POSTGRES_SERVER="db"
REDIS_CACHE_HOST="redis"
REDIS_QUEUE_HOST="redis"
REDIS_RATE_LIMIT_HOST="redis"
```

## Optional Services

The boilerplate includes Redis for caching, job queues, and rate limiting. If running locally without Docker, either:

1. **Install Redis** and keep the default settings
2. **Disable Redis services** (see [User Guide - Configuration](../user-guide/configuration/index.md) for details)

## That's It!

With these basic settings configured, you can start the application:

- **Docker Compose**: `docker compose up`
- **Manual**: `uv run uvicorn src.app.main:app --reload`

For detailed configuration options, advanced settings, and production deployment, see the [User Guide - Configuration](../user-guide/configuration/index.md). 