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
API_CONTACT_NAME=Your name
API_CONTACT_EMAIL=your@email.com
API_LICENSE_NAME=The license you picked
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
# Use "localhost" without Docker
POSTGRES_SERVER=postgres
POSTGRES_PORT=5432
# The default in local and development
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
```

### Sessions

```env
SESSION_TIMEOUT_MINUTES=30
# Unset: the idle timeout is the only one
# SESSION_ABSOLUTE_TIMEOUT_HOURS=12
# Unset: closing an account asks nothing; crudauth's own routes keep their 10-minute default
# FRESH_SIGN_IN_SECONDS=600
SESSION_CLEANUP_INTERVAL_MINUTES=15
MAX_SESSIONS_PER_USER=5
SESSION_SECURE_COOKIES=true
# redis | database | memory
SESSION_BACKEND=redis
# On the cache Redis, apart from the cache DB so a flush won't log users out
SESSION_REDIS_DB=2
# Optional dedicated session Redis, e.g. rediss://user:password@host:6380/0
# SESSION_REDIS_URL=

# CSRF protection (set false to disable in dev/test)
CSRF_ENABLED=true

# Trusted reverse proxies in front of the app (used to resolve the real client
# IP for login lockout). 0 = none; set 1 behind a single nginx/Caddy.
TRUSTED_PROXY_HOPS=0

# Password policy (enforced by crudauth on registration and password changes)
PASSWORD_MIN_LENGTH=8
PASSWORD_REQUIRE_UPPERCASE=true
PASSWORD_REQUIRE_LOWERCASE=true
PASSWORD_REQUIRE_DIGIT=true
PASSWORD_REQUIRE_SPECIAL=true
```

Login lockout is applied by `crudauth`, per client IP and per submitted identifier at once, and answers
`429 Too Many Requests` with a `Retry-After` header. Four settings tune it, passed to crudauth's
`LockoutConfig` in `infrastructure/auth/setup.py`:

```env
# Failures allowed inside the window
LOGIN_MAX_ATTEMPTS=5
# How long failures keep counting
LOGIN_ATTEMPT_WINDOW_SECONDS=900
# First lockout, doubling each round
LOGIN_LOCKOUT_BASE_SECONDS=300
# Cap on the escalation
LOGIN_LOCKOUT_MAX_SECONDS=3600
```

Because both dimensions are counted, an attacker rotating identifiers from one address runs out of
attempts on the address, and one spread across addresses runs out on the identifier.

### First Admin User

The `setup_initial_data` script reads these on first run:

```env
ADMIN_NAME=Admin User
ADMIN_EMAIL=admin@example.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Change-Me-Now-1!
```

Then run:

```bash
uv run --no-sync python -m scripts.setup_initial_data
```

### Cache (Redis or Memcached)

```env
CACHE_ENABLED=true
# The cache.backend the project was generated with
CACHE_BACKEND=redis

# Client-side cache (Cache-Control headers)
CLIENT_CACHE_ENABLED=true
CLIENT_CACHE_MAX_AGE=60

# Redis settings
# Use "localhost" without Docker
CACHE_REDIS_HOST=redis
CACHE_REDIS_PORT=6379
CACHE_REDIS_DB=0
CACHE_REDIS_PASSWORD=
```

### Rate Limiting

```env
RATE_LIMITER_ENABLED=true
# redis, or database (shared), or memory (per process, single worker only)
RATE_LIMITER_BACKEND=redis
DEFAULT_RATE_LIMIT_LIMIT=100
DEFAULT_RATE_LIMIT_PERIOD=60

# Redis (uses DB 1 by default to separate from cache)
# Use "localhost" without Docker
RATE_LIMITER_REDIS_HOST=redis
RATE_LIMITER_REDIS_PORT=6379
RATE_LIMITER_REDIS_DB=1
RATE_LIMITER_REDIS_PASSWORD=
```

API limits are resolved by `crudauth` per request from the user's tier and path. Authenticated
requests are keyed by user ID; anonymous requests are keyed by the client IP, honoring
`TRUSTED_PROXY_HOPS`.

### Background Tasks (Taskiq)

```env
# The taskiq.broker the project was generated with
TASKIQ_BROKER_TYPE=redis

# Redis broker (uses DB 3 by default)
# Use "localhost" without Docker
TASKIQ_REDIS_HOST=redis
TASKIQ_REDIS_PORT=6379
TASKIQ_REDIS_DB=3
TASKIQ_REDIS_PASSWORD=
```

### CORS

```env
CORS_ENABLED=true
# Comma-separated origins
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
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

A provider is wired when both of its settings are set, so you can run Google, GitHub, both or neither; leave a pair empty to disable that provider. See [Authentication](../user-guide/authentication/index.md) for the OAuth setup walkthrough.

The built-in crudauth OAuth router keeps the existing paths (`/api/v1/auth/oauth/{provider}` and
`/api/v1/auth/oauth/callback/{provider}`), returns JSON, sets session cookies, binds state to the
browser, and validates post-login redirects as same-origin relative paths.

### Admin Interface

```env
# Enables SQLAdmin at /admin
ADMIN_ENABLED=true
```

## Docker Compose Settings

When running with Docker Compose, services reach each other by service name. Use these hosts in `.env`:

```env
POSTGRES_SERVER=postgres
CACHE_REDIS_HOST=redis
RATE_LIMITER_REDIS_HOST=redis
TASKIQ_REDIS_HOST=redis
```

## That's It

With these settings, start the app:

=== "Local with uv"

    ```bash
    uv run --no-sync fastapi dev src/interfaces/main.py
    ```

=== "Docker Compose"

    ```bash
    docker compose up
    ```

For the full reference and advanced settings, see [User Guide → Configuration](../user-guide/configuration/index.md).
