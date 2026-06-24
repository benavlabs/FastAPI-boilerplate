# Environment-Specific Configuration

The boilerplate adapts its behavior based on the `ENVIRONMENT` variable. This page covers the recommended settings for each environment and the behaviors the codebase already changes for you.

## Supported Environments

```env
# Options: production, staging, development, local
ENVIRONMENT=development
```

| Value | Intended Use |
|-------|--------------|
| `development` | Local dev with verbose logging and DEBUG-level output |
| `local` | Equivalent to `development` for default config (used by tests / CI) |
| `staging` | Pre-production testing — structured logs, INFO level |
| `production` | Live deployment — JSON logs, security validator on, docs gated |

## What the Codebase Does for You

The boilerplate already changes its own behavior based on `ENVIRONMENT`. You don't need to write conditional code for these:

| Behavior | development / local | staging | production |
|----------|---------------------|---------|------------|
| **Logging style** | Detailed text, color console | Structured key/value | JSON |
| **Default log level** | DEBUG (when `LOG_DEVELOPMENT_VERBOSE=true`) | INFO | WARNING (when `LOG_PRODUCTION_OPTIMIZE=true`) |
| **Noisy library loggers** | Normal level | Normal level | Quieted (urllib3, sqlalchemy, redis, etc.) |
| **Security validator** | Skipped | Skipped | Runs at startup if `PRODUCTION_SECURITY_VALIDATION_ENABLED=true` (default) |
| **Docs at `/docs`** | Available | Available | Disabled unless `ENABLE_DOCS_IN_PRODUCTION=true` |

The logging behavior is driven by `src/infrastructure/logging/config.py`. The security validator lives in `src/infrastructure/security/`.

## Development

For day-to-day local development.

```env
ENVIRONMENT=development
DEBUG=true

# App metadata
APP_NAME=MyApp (Development)
VERSION=0.1.0-dev

# Database (local Postgres or Docker Compose)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=myapp_dev
POSTGRES_SERVER=localhost     # or "db" with Docker Compose
POSTGRES_PORT=5432

# Security — keep a placeholder, never reuse for staging/prod
SECRET_KEY=insecure-dev-key-replace-me

# Sessions — relax cookie security for plain HTTP
SESSION_SECURE_COOKIES=false
CSRF_ENABLED=false             # often easier when testing with curl

# Cache / Rate limiter / Taskiq — point at localhost
CACHE_REDIS_HOST=localhost
RATE_LIMITER_REDIS_HOST=localhost
TASKIQ_REDIS_HOST=localhost

# Looser limits while iterating
DEFAULT_RATE_LIMIT_LIMIT=1000
DEFAULT_RATE_LIMIT_PERIOD=60

# Admin user (used by setup_initial_data on first run)
ADMIN_NAME=Dev Admin
ADMIN_EMAIL=admin@localhost
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

# Logging
LOG_DEVELOPMENT_VERBOSE=true   # gives you DEBUG-level console output
```

!!! tip "Why disable CSRF in dev?"
    The session cookie is HTTP-only and a CSRF token is also returned. Browser-based clients should send both. For curl/Postman testing, setting `CSRF_ENABLED=false` removes one moving piece. Re-enable it when testing the real frontend flow.

## Staging

A pre-production rehearsal — same code paths as production, separate data, useful for catching environment-specific issues.

```env
ENVIRONMENT=staging
DEBUG=false

APP_NAME=MyApp (Staging)
VERSION=0.1.0-staging

POSTGRES_USER=staging_user
POSTGRES_PASSWORD=use-a-strong-password
POSTGRES_SERVER=staging-db.example.com
POSTGRES_PORT=5432
POSTGRES_DB=myapp_staging

# Real key, distinct from prod
SECRET_KEY=<openssl rand -hex 32>

# Lock cookies and CSRF down
SESSION_SECURE_COOKIES=true
CSRF_ENABLED=true

# Restrict CORS to staging domains
CORS_ORIGINS=https://staging.example.com
CORS_ALLOW_METHODS=GET,POST,PUT,DELETE,PATCH
CORS_ALLOW_HEADERS=Authorization,Content-Type

# Real Redis hostnames — use separate DBs for cache/rate limit/taskiq
CACHE_REDIS_HOST=staging-redis.example.com
CACHE_REDIS_PASSWORD=<from secrets manager>
RATE_LIMITER_REDIS_HOST=staging-redis.example.com
RATE_LIMITER_REDIS_PASSWORD=<from secrets manager>
TASKIQ_REDIS_HOST=staging-redis.example.com
TASKIQ_REDIS_PASSWORD=<from secrets manager>

DEFAULT_RATE_LIMIT_LIMIT=100
DEFAULT_RATE_LIMIT_PERIOD=60

ADMIN_NAME=Staging Admin
ADMIN_EMAIL=admin@staging.example.com
ADMIN_USERNAME=staging_admin
ADMIN_PASSWORD=<from secrets manager>

# Logging — staging picks INFO automatically; can opt into file output
LOG_FILE_ENABLED=true
LOG_FILE_PATH=logs/app.log
```

## Production

Live traffic. Treat every setting as security-relevant.

```env
ENVIRONMENT=production
DEBUG=false

APP_NAME=MyApp
VERSION=1.0.0
CONTACT_NAME=Support Team
CONTACT_EMAIL=support@example.com

POSTGRES_USER=prod_user
POSTGRES_PASSWORD=<from secrets manager>
POSTGRES_SERVER=prod-db.example.com
POSTGRES_PORT=5432
POSTGRES_DB=myapp_production

# Generated with: python -c "import secrets; print(secrets.token_urlsafe(64))"
SECRET_KEY=<from secrets manager>

# Production security validator is on by default
PRODUCTION_SECURITY_VALIDATION_ENABLED=true
PRODUCTION_SECURITY_STRICT_MODE=true

# Sessions
SESSION_SECURE_COOKIES=true
SESSION_TIMEOUT_MINUTES=30
SESSION_BACKEND=redis
CSRF_ENABLED=true
# Trusted reverse proxies in front of the app, so crudauth keys login lockout on
# the real client IP. Set 1 behind a single nginx/Caddy, 2 if Cloudflare is also in front.
TRUSTED_PROXY_HOPS=1

# Strict CORS
CORS_ORIGINS=https://example.com,https://www.example.com
CORS_ALLOW_METHODS=GET,POST,PUT,DELETE,PATCH
CORS_ALLOW_HEADERS=Authorization,Content-Type

# Docs gated off by default in production
ENABLE_DOCS_IN_PRODUCTION=false

# Real Redis with passwords; separate DBs per concern
CACHE_REDIS_HOST=prod-redis.example.com
CACHE_REDIS_PASSWORD=<from secrets manager>
CACHE_REDIS_DB=0
RATE_LIMITER_REDIS_HOST=prod-redis.example.com
RATE_LIMITER_REDIS_PASSWORD=<from secrets manager>
RATE_LIMITER_REDIS_DB=1
TASKIQ_REDIS_HOST=prod-redis.example.com
TASKIQ_REDIS_PASSWORD=<from secrets manager>
TASKIQ_REDIS_DB=3

DEFAULT_RATE_LIMIT_LIMIT=100
DEFAULT_RATE_LIMIT_PERIOD=60

# Admin (used by setup_initial_data only on first deploy)
ADMIN_NAME=System Administrator
ADMIN_EMAIL=admin@example.com
ADMIN_USERNAME=sysadmin
ADMIN_PASSWORD=<from secrets manager>

# Logging — production picks JSON automatically; LOG_PRODUCTION_OPTIMIZE quiets noisy libs
LOG_PRODUCTION_OPTIMIZE=true
LOG_FILE_ENABLED=true
LOG_FILE_PATH=/var/log/app/app.log
```

!!! danger "Production Security Validator"
    With `ENVIRONMENT=production` and `PRODUCTION_SECURITY_VALIDATION_ENABLED=true` (both default), the app refuses to start if it finds insecure settings — e.g. the placeholder `SECRET_KEY`, `DEBUG=true`, `CORS_ORIGINS=*`. Set `PRODUCTION_SECURITY_STRICT_MODE=true` to make it stricter still.

## Detecting the Environment in Code

`src/infrastructure/config/enums.py` defines `EnvironmentOption` so you don't have to compare against magic strings:

```python
from src.infrastructure.config.settings import EnvironmentOption, get_settings

settings = get_settings()

if settings.ENVIRONMENT == EnvironmentOption.PRODUCTION:
    # production-only code
    ...
```

For helpers, add small properties to your own settings class — but for most cases the above is enough. Avoid scattering environment branches in business logic; keep them at startup or in middleware.

## Managing Multiple Environments

### One `.env` per environment

The simplest approach. Keep `.env.development`, `.env.staging`, `.env.production` *outside* version control (e.g. in a secrets manager) and symlink the active one:

```bash
# Switch environments locally
ln -sf .env.staging backend/.env
```

For staging/production you'd more typically:

- Pull secrets from a manager (AWS Secrets Manager, Vault, Doppler, 1Password) at deploy time
- Render the `.env` file from CI, or set env vars directly on the runtime (Kubernetes, ECS, systemd unit, etc.)

### Docker Compose Overrides

For Compose, use overlay files:

```bash
# Development: docker-compose.yml + docker-compose.override.yml (auto-loaded)
docker compose up

# Staging
docker compose -f docker-compose.yml -f docker-compose.staging.yml up

# Production
docker compose -f docker-compose.yml -f docker-compose.production.yml up
```

The override files only need to specify what *changes* (target stage, removed dev volumes, scaling, secrets), not the full service definition.

## Validating Configuration

Run a quick check that the app reads what you think:

```bash
cd backend
uv run python -c "
from src.infrastructure.config.settings import get_settings
s = get_settings()
print(f'env       : {s.ENVIRONMENT}')
print(f'debug     : {s.DEBUG}')
print(f'app       : {s.APP_NAME} v{s.VERSION}')
print(f'db host   : {s.POSTGRES_SERVER}:{s.POSTGRES_PORT}/{s.POSTGRES_DB}')
print(f'cache     : {s.CACHE_BACKEND} -> {s.CACHE_REDIS_HOST}:{s.CACHE_REDIS_PORT}')
print(f'cors      : {s.CORS_ORIGINS}')
print(f'sessions  : secure={s.SESSION_SECURE_COOKIES} csrf={s.CSRF_ENABLED}')
"
```

For production deployment specifically, the security validator runs at startup — if it fails, the app exits before binding the port. That's the strongest signal.

## Best Practices

### Security
- Generate a fresh `SECRET_KEY` per environment (never reuse)
- Pull secrets from a manager, not files committed to git
- Always set `SESSION_SECURE_COOKIES=true` outside development
- Restrict `CORS_ORIGINS` to your real domains in staging/production
- Set Redis passwords for staging/production
- Leave `PRODUCTION_SECURITY_VALIDATION_ENABLED=true` in production

### Performance
- Use Redis (not Memcached) when you need persistence or multi-DB separation
- Set distinct Redis DB numbers for cache/rate-limit/taskiq (defaults 0/1/3)
- Tune `POSTGRES_POOL_SIZE` for your workload (default 20)
- Increase `TASKIQ_WORKER_CONCURRENCY` if jobs are I/O-bound

### Operations
- Keep environment-specific values in your secrets manager, not env files
- Document any custom env vars you add in `.env.example`
- Test deployments in staging before production
- Monitor the logs at startup — the security validator will tell you what's wrong

## See Also

- **[Environment Variables](environment-variables.md)** — Complete reference of every variable
- **[Settings Classes](settings-classes.md)** — How variables become Python settings
- **[Docker Setup](docker-setup.md)** — Compose configuration per environment
- **[Production](../production.md)** — Production deployment guide
