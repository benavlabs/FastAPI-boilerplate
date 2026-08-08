# Environment Variables Reference

This page is the complete reference for every environment variable the boilerplate reads. The source of truth is `backend/.env.example` — this page mirrors it with descriptions.

All variables are loaded from `backend/.env` at application startup via Pydantic `BaseSettings` classes in `src/infrastructure/config/settings.py`.

## Environment

```env
# Options: development, staging, production, local
ENVIRONMENT=development
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENVIRONMENT` | `development` | Drives logging style, docs visibility, and security validation. See [Environment-Specific](environment-specific.md). |

## Database

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=postgres
POSTGRES_SERVER=db          # use "localhost" without Docker
POSTGRES_PORT=5432
POSTGRES_SYNC_PREFIX=postgresql://
POSTGRES_ASYNC_PREFIX=postgresql+asyncpg://
CREATE_TABLES_ON_STARTUP=true
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `POSTGRES_USER` | `postgres` | Database user |
| `POSTGRES_PASSWORD` | `postgres` | Database password |
| `POSTGRES_DB` | `postgres` | Database name |
| `POSTGRES_SERVER` | `localhost` | Hostname (use `db` for Compose) |
| `POSTGRES_PORT` | `5432` | TCP port |
| `POSTGRES_SYNC_PREFIX` | `postgresql://` | Driver prefix for sync code (Alembic) |
| `POSTGRES_ASYNC_PREFIX` | `postgresql+asyncpg://` | Driver prefix for async code (the app) |
| `CREATE_TABLES_ON_STARTUP` | `true` | Auto-create tables from models on startup |
| `POSTGRES_POOL_SIZE` | `20` | SQLAlchemy connection pool size |
| `POSTGRES_MAX_OVERFLOW` | `0` | Pool overflow connections |
| `POSTGRES_POOL_PRE_PING` | `true` | Test a pooled connection before use, replacing ones the server has dropped |
| `POSTGRES_POOL_RECYCLE` | `-1` | Discard connections older than N seconds (`-1` disables) |

If you set `DATABASE_URL` directly, it overrides the constructed URL — use it whenever the connection needs more than host/port/credentials, such as a managed provider that requires TLS:

```env
DATABASE_URL=postgresql+asyncpg://user:password@host.example.com/dbname?ssl=require
```

The URL must use the `postgresql+asyncpg://` prefix, and query parameters are passed to `asyncpg` (which spells TLS `ssl=require`, not libpq's `sslmode=require`). The [production validator](../production.md#the-production-validator) reads the credentials out of the URL, so the `POSTGRES_*` variables can keep their defaults. See [Neon](../database/neon.md) for a full walkthrough with a serverless provider.

## Cache

```env
CACHE_ENABLED=true
CACHE_BACKEND=redis           # or "memcached"
DEFAULT_CACHE_EXPIRATION=3600

# Client-side cache (Cache-Control headers)
CLIENT_CACHE_ENABLED=true
CLIENT_CACHE_MAX_AGE=60
```

### Redis backend

```env
CACHE_REDIS_HOST=redis        # use "localhost" without Docker
CACHE_REDIS_PORT=6379
CACHE_REDIS_DB=0
CACHE_REDIS_PASSWORD=
CACHE_REDIS_CONNECT_TIMEOUT=5
CACHE_REDIS_POOL_SIZE=10
```

### Memcached backend

```env
CACHE_MEMCACHED_HOST=localhost
CACHE_MEMCACHED_PORT=11211
CACHE_MEMCACHED_POOL_SIZE=10
CACHE_MEMCACHED_CONNECT_TIMEOUT=5
```

## Rate Limiting

```env
RATE_LIMITER_ENABLED=true
RATE_LIMITER_BACKEND=redis     # or "memcached"
RATE_LIMITER_FAIL_OPEN=true    # allow requests when backend is unreachable
DEFAULT_RATE_LIMIT_LIMIT=100
DEFAULT_RATE_LIMIT_PERIOD=60
```

### Redis backend

```env
RATE_LIMITER_REDIS_HOST=redis
RATE_LIMITER_REDIS_PORT=6379
RATE_LIMITER_REDIS_DB=1        # separate DB from cache (DB 0)
RATE_LIMITER_REDIS_PASSWORD=
RATE_LIMITER_REDIS_CONNECT_TIMEOUT=5
RATE_LIMITER_REDIS_POOL_SIZE=10
```

### Memcached backend

```env
RATE_LIMITER_MEMCACHED_HOST=localhost
RATE_LIMITER_MEMCACHED_PORT=11211
RATE_LIMITER_MEMCACHED_POOL_SIZE=10
```

## Background Tasks (Taskiq)

```env
TASKIQ_ENABLED=true
TASKIQ_BROKER_TYPE=redis        # or "rabbitmq"
```

### Redis broker

```env
TASKIQ_REDIS_HOST=redis
TASKIQ_REDIS_PORT=6379
TASKIQ_REDIS_DB=3               # separate DB from cache and rate limiter
TASKIQ_REDIS_PASSWORD=
```

### RabbitMQ broker

```env
TASKIQ_RABBITMQ_HOST=localhost
TASKIQ_RABBITMQ_PORT=5672
TASKIQ_RABBITMQ_USER=guest
TASKIQ_RABBITMQ_PASSWORD=guest
TASKIQ_RABBITMQ_VHOST=/
```

### Worker tuning

```env
TASKIQ_WORKER_CONCURRENCY=2
TASKIQ_MAX_TASKS_PER_WORKER=1000
```

## Web Server

### CORS

```env
CORS_ENABLED=true
CORS_ORIGINS=*                  # comma-separated list of origins
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=*
CORS_ALLOW_HEADERS=*
```

!!! danger "CORS in Production"
    Never use `*` for `CORS_ORIGINS` in production. Specify exact domains:
    ```env
    CORS_ORIGINS=https://yourapp.com,https://www.yourapp.com
    CORS_ALLOW_METHODS=GET,POST,PUT,DELETE,PATCH
    CORS_ALLOW_HEADERS=Authorization,Content-Type
    ```

### Compression

```env
GZIP_ENABLED=true
GZIP_MINIMUM_SIZE=1000
```

### API Docs

```env
ENABLE_DOCS_IN_PRODUCTION=false  # serve /docs even when ENVIRONMENT=production
OPENAPI_PREFIX=                   # path prefix for the OpenAPI schema
```

## Authentication & Security

```env
SECRET_KEY=insecure-secret-key-change-this-in-production

# Production security validation (enabled by default in production)
PRODUCTION_SECURITY_VALIDATION_ENABLED=true
PRODUCTION_SECURITY_STRICT_MODE=false
```

Generate a strong key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Sessions

```env
SESSION_TIMEOUT_MINUTES=30
SESSION_CLEANUP_INTERVAL_MINUTES=15
MAX_SESSIONS_PER_USER=5
SESSION_SECURE_COOKIES=true
SESSION_BACKEND=redis            # redis | memory

# Number of trusted reverse proxies in front of the app. crudauth uses this to
# resolve the real client IP (from X-Forwarded-For) for login lockout.
# 0 = no proxy; set 1 behind a single nginx/Caddy, 2 if Cloudflare is also in front.
TRUSTED_PROXY_HOPS=0
```

### CSRF

```env
# Set false to disable CSRF validation in dev/test
CSRF_ENABLED=true
```

### Login Lockout

There are no env vars for login throttling. `crudauth` applies an escalating per-IP / per-identifier lockout internally and returns `429 Too Many Requests` with a `Retry-After` header once the threshold is hit. Behind a proxy, set `TRUSTED_PROXY_HOPS` (above) so the lockout keys on the real client IP rather than the proxy's.

### OAuth

```env
OAUTH_REDIRECT_BASE_URL=http://localhost:8000

# Google OAuth (leave empty to disable)
OAUTH_GOOGLE_CLIENT_ID=
OAUTH_GOOGLE_CLIENT_SECRET=

# GitHub OAuth (data model anticipates it; no provider/routes wired — see Authentication)
OAUTH_GITHUB_CLIENT_ID=
OAUTH_GITHUB_CLIENT_SECRET=
```

## Admin Interface (SQLAdmin)

```env
ADMIN_ENABLED=true              # enables /admin
```

## Application Metadata

```env
DEBUG=false
APP_NAME=FastAPI Boilerplate
APP_DESCRIPTION=Modular FastAPI starter
VERSION=0.19.0
CONTACT_NAME=Support
CONTACT_EMAIL=support@example.com
LICENSE_NAME=MIT
```

### API Settings (optional overrides)

```env
# API_PREFIX=/api
# DOCS_URL=/docs
# REDOC_URL=/redoc
```

## Initial Setup

These are read by `python -m scripts.setup_initial_data`:

```env
ADMIN_NAME=Admin User
ADMIN_EMAIL=admin@example.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
```

The default tier name is also configurable (defaults to `free`):

```env
DEFAULT_TIER_NAME=free
```

## Logging

```env
LOG_LEVEL=INFO
LOG_FORMAT=structured           # simple | detailed | structured | json
LOG_CONSOLE_ENABLED=true
LOG_FILE_ENABLED=false
LOG_FILE_PATH=logs/app.log
LOG_FILE_MAX_SIZE=10485760      # 10 MB
LOG_FILE_BACKUP_COUNT=5
LOG_CORRELATION_ID=true
LOG_STRUCTURED_CONTEXT=true
LOG_PERFORMANCE_METRICS=false
LOG_SQL_QUERIES=false
LOG_INCLUDE_STACKTRACE=true
LOG_DEVELOPMENT_VERBOSE=true
LOG_PRODUCTION_OPTIMIZE=true
```

## Production Security Checklist

Before deploying to production:

1. Generate a strong `SECRET_KEY` (at least 64 bytes of entropy)
2. Use unique passwords for the database and every Redis instance
3. Use separate Redis databases for each service (`CACHE_REDIS_DB=0`, `RATE_LIMITER_REDIS_DB=1`, `TASKIQ_REDIS_DB=3`)
4. Restrict `CORS_ORIGINS` to your real domains (no `*`)
5. Set strong admin credentials (`ADMIN_USERNAME`, `ADMIN_PASSWORD`)
6. Review session timeouts for your security posture
7. Set `ENVIRONMENT=production` to enable the security validator
8. If using RabbitMQ, replace the `guest/guest` defaults

## Troubleshooting

### Variables Not Loading

```bash
# Check the file location
ls -la backend/.env

# Make sure there are no spaces around =
grep "=" backend/.env | head -5

# Verify what Python sees
cd backend
uv run python -c "from src.infrastructure.config.settings import get_settings; s = get_settings(); print(s.APP_NAME, s.ENVIRONMENT)"
```

### Database Connection Failed

```bash
# Linux
sudo systemctl status postgresql
psql -h localhost -U postgres -d postgres

# macOS
brew services list | grep postgresql
```

### Redis Connection Failed

```bash
redis-cli -h localhost -p 6379 ping  # should print PONG

# Linux
sudo systemctl status redis-server

# macOS
brew services list | grep redis
```

## See Also

- **[Settings Classes](settings-classes.md)** — How env vars are turned into Python settings
- **[Docker Setup](docker-setup.md)** — Compose configuration
- **[Environment-Specific](environment-specific.md)** — Recommended values per environment
