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
POSTGRES_SERVER=postgres    # use "localhost" without Docker
POSTGRES_PORT=5432
POSTGRES_ASYNC_PREFIX=postgresql+asyncpg://
CREATE_TABLES_ON_STARTUP=true   # on by default in local and development only
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `POSTGRES_USER` | `postgres` | Database user |
| `POSTGRES_PASSWORD` | `postgres` | Database password |
| `POSTGRES_DB` | `postgres` | Database name |
| `POSTGRES_SERVER` | `localhost` | Hostname (use `postgres`, the Compose service name) |
| `POSTGRES_PORT` | `5432` | TCP port |
| `POSTGRES_ASYNC_PREFIX` | `postgresql+asyncpg://` | Driver prefix for async code (the app) |
| `CREATE_TABLES_ON_STARTUP` | `true` in local and development, `false` otherwise | Auto-create tables from models on startup; production refuses `true` |
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

Provided by `crudauth`, on Redis or in memory. Limits are resolved per request from
the user's tier and path, falling back to the defaults below, and each path keeps its own counter.

```env
RATE_LIMITER_ENABLED=true
RATE_LIMITER_BACKEND=redis        # or memory (per process, single worker only)
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

## Email

```env
EMAIL_BACKEND=console           # or "smtp"
EMAIL_FROM=no-reply@localhost
EMAIL_FROM_NAME=
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `EMAIL_BACKEND` | `console` | `console` logs each message and sends nothing; `smtp` delivers. Production refuses `console` |
| `EMAIL_FROM` | `no-reply@localhost` | The address the account emails come from |
| `EMAIL_FROM_NAME` | empty | The display name beside it |

### SMTP

```env
EMAIL_SMTP_HOST=
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=
EMAIL_SMTP_PASSWORD=
EMAIL_SMTP_STARTTLS=true
EMAIL_SMTP_TIMEOUT_SECONDS=10
```

`EMAIL_BACKEND=smtp` with no `EMAIL_SMTP_HOST` is refused by name when the sender is built.
`EMAIL_SMTP_STARTTLS` verifies the server's certificate and hostname, so a server presenting a
self-signed certificate is refused rather than trusted; turn it off only for a relay on a network
you own. With the taskiq feature present, delivery is enqueued as the `email:send` task and a worker
does the sending, so no request waits on the mail server.

## Background Tasks (Taskiq)

```env
TASKIQ_BROKER_TYPE=redis        # or "rabbitmq"
TASKIQ_DEFAULT_RETRY_COUNT=3    # runs in all for a task labelled retry_on_error=True; 0 turns retries off
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

## Web Server

### CORS

```env
CORS_ENABLED=true
CORS_ORIGINS=http://localhost:3000,http://localhost:5173  # comma-separated list of origins
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=*
CORS_ALLOW_HEADERS=*
```

!!! danger "CORS in Production"
    Never use `*` for `CORS_ORIGINS` in production: any website could call the API from your users' browsers. The app drops `CORS_ALLOW_CREDENTIALS` while `*` is listed, so a page on another origin can't read a response to a call it made with the user's cookies — which is also why a wildcard origin can't serve a logged-in frontend. A simple cross-site request is still delivered, cookie included wherever `SameSite` allows it; the browser only withholds the response. The production security validator refuses to start with it. Specify exact domains:
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
ENABLE_DOCS_IN_PRODUCTION=false  # serve /docs even when ENVIRONMENT=production (superuser-only)
OPENAPI_PREFIX=                   # path prefix for the OpenAPI schema
```

When docs are served outside development (staging, or production with `ENABLE_DOCS_IN_PRODUCTION=true`), the built-in FastAPI docs routes are not registered — `/docs`, `/redoc`, and `/openapi.json` are only reachable through the app's own routes, which require superuser authentication.

## Authentication & Security

```env
SECRET_KEY=insecure-secret-key-change-this-in-production

# Production security validation (enabled by default in production)
PRODUCTION_SECURITY_VALIDATION_ENABLED=true
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

LOGIN_MAX_ATTEMPTS=5             # failures allowed inside the window, per address and per account
LOGIN_ATTEMPT_WINDOW_SECONDS=900 # how long failures keep counting
LOGIN_LOCKOUT_BASE_SECONDS=300   # first lockout, doubling each round
LOGIN_LOCKOUT_MAX_SECONDS=3600   # ceiling for the doubling
SESSION_BACKEND=redis            # redis | memory
SESSION_REDIS_DB=2               # on the cache Redis, apart from the cache DB so a flush won't log users out
# SESSION_REDIS_URL=             # optional dedicated session Redis, e.g. rediss://user:password@host:6380/0

# Number of trusted reverse proxies in front of the app. crudauth uses this to
# resolve the real client IP (from X-Forwarded-For) for login lockout.
# 0 = no proxy; set 1 behind a single nginx/Caddy, 2 if Cloudflare is also in front.
TRUSTED_PROXY_HOPS=0
```

### Forwarded Headers

```env
# Which peers uvicorn accepts X-Forwarded-For and X-Forwarded-Proto from.
FORWARDED_ALLOW_IPS=172.31.240.0/24
```

`FORWARDED_ALLOW_IPS` is read by **uvicorn**, not by the app, and it decides what `request.client`
and the access logs report. Because uvicorn reads it from its own process environment, it reaches
the server through compose's `env_file` (or whatever exports it where uvicorn starts) rather than
through the app's settings — a value in `backend/.env` only applies if that file is the container's
`env_file`. `bp deploy generate nginx` writes it for you, set to `--internal-subnet`.

Leave it unset when nothing sits in front of the app. A wildcard (`*`) lets any client claim any
address, and `TRUSTED_PROXY_HOPS` then counts hops in a header the client controls.

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
ADMIN_ENABLED=true              # enables the panel
ADMIN_BASE_URL=/admin           # where it is mounted, and the admin cookie's path
```

## Application Metadata

```env
DEBUG=false
APP_NAME=FastAPI Boilerplate
APP_DESCRIPTION=Modular FastAPI starter
VERSION=0.1.0
API_CONTACT_NAME=Support
API_CONTACT_EMAIL=support@example.com
API_LICENSE_NAME=MIT
```

`API_TITLE`, `API_DESCRIPTION` and `API_VERSION` override `APP_NAME`, `APP_DESCRIPTION` and
`VERSION` in the OpenAPI document. A field left empty is left out of it, so a new project names no
contact and no licence until it sets its own.

### API Settings (optional overrides)

```env
# API_PREFIX=/api
# DOCS_URL=/docs
# REDOC_URL=/redoc
```

`API_PREFIX` must start with `/` and must not end with `/`; anything else is refused when the
settings load. It moves every API route, the OAuth routes and the `no-store` cache header with it.

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
LOG_FORMAT=                     # console only: simple | detailed | structured | json; empty = the environment's default
LOG_CONSOLE_ENABLED=true
LOG_FILE_ENABLED=false
LOG_FILE_PATH=logs/app.log
LOG_FILE_MAX_SIZE=10485760      # 10 MB
LOG_FILE_BACKUP_COUNT=5
LOG_DEVELOPMENT_VERBOSE=true
LOG_PRODUCTION_OPTIMIZE=true
```

`LOG_FORMAT` names the console format only; a log file is written in its environment's own format,
which is what a collector reading it expects. A value no formatter implements is refused when the
settings load.

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
uv run --no-sync python -c "from src.infrastructure.config.settings import get_settings; s = get_settings(); print(s.APP_NAME, s.ENVIRONMENT)"
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
