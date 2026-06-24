# Configuration

This guide covers the essential configuration steps to get your FastAPI application running.

## Quick Setup

Copy the example environment file and edit a few values:

```bash
cd backend
cp .env.example .env
```

The full set of variables lives in `backend/.env.example`. The sections below cover the ones you'll most likely want to change.

## Essential Configuration

Open `backend/.env` and set these required values.

### Application Settings

```env
APP_NAME=Your app name here
APP_DESCRIPTION=Your app description here
VERSION=0.1.0
CONTACT_NAME=Your name
CONTACT_EMAIL=your@email.com
LICENSE_NAME=The license you picked
```

### Environment Type

```env
# Options: development, staging, production, local
ENVIRONMENT=development
```

- **development**: API docs at `/docs`, `/redoc`, verbose logging
- **staging**: Structured logs, file output enabled
- **production**: JSON logs, security validation, docs gated by `ENABLE_DOCS_IN_PRODUCTION`
- **local**: Same defaults as development; useful for tests

### Database

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=changeme
POSTGRES_DB=postgres
POSTGRES_SERVER=db          # use "localhost" without Docker
POSTGRES_PORT=5432
CREATE_TABLES_ON_STARTUP=true
```

### Security

Generate a strong `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

```env
SECRET_KEY=your-generated-secret-key-here

# Production security validation (enabled by default in production)
PRODUCTION_SECURITY_VALIDATION_ENABLED=true
PRODUCTION_SECURITY_STRICT_MODE=false
```

### Sessions

```env
SESSION_TIMEOUT_MINUTES=30
SESSION_CLEANUP_INTERVAL_MINUTES=15
MAX_SESSIONS_PER_USER=5
SESSION_SECURE_COOKIES=true
SESSION_BACKEND=redis            # redis | memory

# CSRF protection (set false to disable in dev/test)
CSRF_ENABLED=true

# Trusted reverse proxies in front of the app (used to resolve the real client
# IP for login lockout). 0 = none; set 1 behind a single nginx/Caddy.
TRUSTED_PROXY_HOPS=0
```

Login lockout is handled by `crudauth` itself: it applies an escalating per-IP / per-identifier lockout and returns `429 Too Many Requests` with a `Retry-After` header. There are no `LOGIN_MAX_ATTEMPTS` / `LOGIN_WINDOW_MINUTES` knobs to set.

### First Admin User

The `setup_initial_data` script reads these on first run:

```env
ADMIN_NAME=Admin User
ADMIN_EMAIL=admin@example.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
```

Then run:

```bash
uv run python -m scripts.setup_initial_data
```

### Cache (Redis or Memcached)

```env
CACHE_ENABLED=true
CACHE_BACKEND=redis             # or "memcached"
DEFAULT_CACHE_EXPIRATION=3600

# Client-side cache (Cache-Control headers)
CLIENT_CACHE_ENABLED=true
CLIENT_CACHE_MAX_AGE=60

# Redis settings
CACHE_REDIS_HOST=redis          # use "localhost" without Docker
CACHE_REDIS_PORT=6379
CACHE_REDIS_DB=0
CACHE_REDIS_PASSWORD=
```

### Rate Limiting

```env
RATE_LIMITER_ENABLED=true
RATE_LIMITER_BACKEND=redis      # or "memcached"
RATE_LIMITER_FAIL_OPEN=true
DEFAULT_RATE_LIMIT_LIMIT=100
DEFAULT_RATE_LIMIT_PERIOD=60

# Redis (uses DB 1 by default to separate from cache)
RATE_LIMITER_REDIS_HOST=redis   # use "localhost" without Docker
RATE_LIMITER_REDIS_PORT=6379
RATE_LIMITER_REDIS_DB=1
RATE_LIMITER_REDIS_PASSWORD=
```

### Background Tasks (Taskiq)

```env
TASKIQ_ENABLED=true
TASKIQ_BROKER_TYPE=redis        # or "rabbitmq"

# Redis broker (uses DB 3 by default)
TASKIQ_REDIS_HOST=redis         # use "localhost" without Docker
TASKIQ_REDIS_PORT=6379
TASKIQ_REDIS_DB=3
TASKIQ_REDIS_PASSWORD=

TASKIQ_WORKER_CONCURRENCY=2
TASKIQ_MAX_TASKS_PER_WORKER=1000
```

### CORS

```env
CORS_ENABLED=true
CORS_ORIGINS=*                  # comma-separated origins
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=*
CORS_ALLOW_HEADERS=*
```

!!! warning "CORS in Production"
    Never use `*` for `CORS_ORIGINS` in production. Specify exact domains and explicit methods/headers:

    ```env
    CORS_ORIGINS=https://yourapp.com,https://www.yourapp.com
    CORS_ALLOW_METHODS=GET,POST,PUT,DELETE,PATCH
    CORS_ALLOW_HEADERS=Authorization,Content-Type
    ```

### OAuth (Optional)

For Google / GitHub sign-in:

```env
OAUTH_REDIRECT_BASE_URL=http://localhost:8000

# Google OAuth
OAUTH_GOOGLE_CLIENT_ID=
OAUTH_GOOGLE_CLIENT_SECRET=

# GitHub OAuth
OAUTH_GITHUB_CLIENT_ID=
OAUTH_GITHUB_CLIENT_SECRET=
```

Leave the credentials empty to disable a provider. See [Authentication](../user-guide/authentication/index.md) for the OAuth setup walkthrough.

### Admin Interface

```env
ADMIN_ENABLED=true              # enables SQLAdmin at /admin
```

## Docker Compose Settings

When running with Docker Compose, services reach each other by service name. Use these hosts in `.env`:

```env
POSTGRES_SERVER=db
CACHE_REDIS_HOST=redis
RATE_LIMITER_REDIS_HOST=redis
TASKIQ_REDIS_HOST=redis
```

## That's It

With these settings, start the app:

=== "Local with uv"

    ```bash
    uv run fastapi dev src/interfaces/main.py
    ```

=== "Docker Compose"

    ```bash
    docker compose up
    ```

For the full reference and advanced settings, see [User Guide → Configuration](../user-guide/configuration/index.md).
