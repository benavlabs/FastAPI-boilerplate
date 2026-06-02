# Production Deployment

This page is the production hardening checklist for a FastAPI-boilerplate deployment. It covers the boilerplate's built-in production validators, env-var hygiene, the multi-stage Dockerfile that ships, and the operational decisions you'll make once.

## The Production Validator

When `ENVIRONMENT=production`, `infrastructure/security/production_validator.py` runs at startup and refuses to boot the app on critical issues. Two tiers:

### Critical (raises `ProductionSecurityError`, app exits)

The app **will not start** if any of these is true:

- **`SECRET_KEY` is insecure.** Default placeholder, < 32 chars, contains an obvious string ("password", "secret", "test", "dev", "default", etc.), or has a predictable pattern (repetition, all-same-char).
- **`POSTGRES_PASSWORD=postgres`** (the well-known default). Attackers try this first.
- **`POSTGRES_PASSWORD` is empty.** Database is unprotected.

### Warnings (logged, app starts)

These don't block startup but you should fix them before the app sees real traffic:

- **Redis without a password** (`CACHE_REDIS_PASSWORD`, `SESSION_REDIS_PASSWORD`, `RATE_LIMITER_REDIS_PASSWORD`, `TASKIQ_REDIS_PASSWORD` all unset)
- **`CORS_ORIGINS=*`** — allows any origin to send credentialed requests
- **`DEBUG=true`** — exposes stack traces in error responses
- **API docs (`/docs`, `/redoc`) reachable** — see "Documentation" below
- **Session config too loose** (cookies not marked `Secure`, very long max-age, etc.)
- **Weak admin credentials** (default username/password patterns)

The validator is **not** a substitute for a thorough threat model — it catches the most common deployment mistakes, not all of them. Treat it as a smoke test.

## Production `.env` Checklist

Generate a `.env` for production from `backend/.env.example`. The bare-minimum changes:

```env
# Environment
ENVIRONMENT=production
DEBUG=false

# App
APP_NAME="Your Production App"
VERSION=1.0.0

# Secrets — generate a fresh, unique value
SECRET_KEY=<openssl rand -hex 32>

# Database — never use defaults
POSTGRES_USER=app_prod
POSTGRES_PASSWORD=<long-random-secret>
POSTGRES_SERVER=<your-db-host>
POSTGRES_PORT=5432
POSTGRES_DB=app_prod

# Auto-creating tables in prod is dangerous; use Alembic instead
CREATE_TABLES_ON_STARTUP=false

# Migrations: must be opted into, even with the right env
CONFIRM_PRODUCTION_MIGRATION=yes      # only when actively running migrations

# CORS — list the exact origins that can call your API
CORS_ORIGINS=["https://app.example.com","https://admin.example.com"]

# Cache (Redis or Memcached)
CACHE_ENABLED=true
CACHE_BACKEND=redis
CACHE_REDIS_HOST=<redis-host>
CACHE_REDIS_PASSWORD=<redis-password>

# Sessions
SESSION_BACKEND=redis
SESSION_REDIS_HOST=<redis-host>
SESSION_REDIS_PASSWORD=<redis-password>
SESSION_SECURE_COOKIES=true            # required when serving over HTTPS
CSRF_ENABLED=true

# Rate limiting
RATE_LIMITER_ENABLED=true
RATE_LIMITER_BACKEND=redis
RATE_LIMITER_REDIS_HOST=<redis-host>
RATE_LIMITER_REDIS_PASSWORD=<redis-password>
RATE_LIMITER_FAIL_OPEN=true            # let traffic through when Redis errors

# Taskiq
TASKIQ_ENABLED=true
TASKIQ_BROKER_TYPE=redis
TASKIQ_REDIS_HOST=<redis-host>
TASKIQ_REDIS_PASSWORD=<redis-password>

# Admin panel
ADMIN_ENABLED=false                    # safest default in prod
ADMIN_USERNAME=<unique-username>
ADMIN_PASSWORD=<long-random-secret>

# Documentation
OPENAPI_URL=                           # disable /docs and /redoc

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

Notes worth calling out:

- **`CREATE_TABLES_ON_STARTUP=false`** — production should run schema changes via Alembic, not by `Base.metadata.create_all` on every boot.
- **`CONFIRM_PRODUCTION_MIGRATION=yes`** — `migrations/env.py` calls `validate_production_migration` which **refuses** to run migrations against production unless this is explicitly set. Ship deployment commands with it; never set it in long-lived env files.
- **`SESSION_SECURE_COOKIES=true`** — cookies are sent only over HTTPS. Required if you're terminating TLS at a proxy.
- **`OPENAPI_URL=`** (empty) disables the Swagger UI and OpenAPI spec entirely. The validator warns when this is exposed in production.

See [Configuration → Environment-Specific](configuration/environment-specific.md) for the full per-environment matrix.

## Generating a Strong `SECRET_KEY`

```bash
openssl rand -hex 32
```

Or:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Never reuse the dev key. Never commit prod keys. Pull from a secrets manager (AWS Secrets Manager, HashiCorp Vault, Doppler, etc.) at deploy time — `.env` files on disk are an audit-trail problem.

## The Production Dockerfile

The boilerplate ships a multi-stage `backend/Dockerfile`:

| Stage              | Purpose                                          |
|--------------------|--------------------------------------------------|
| `requirements-stage` | Exports pinned requirements from `uv.lock`     |
| `base`             | Production base — copies source, installs deps  |
| `dev`              | Adds dev deps, mounts tests, runs `fastapi dev` |
| `migrate`          | Runs `alembic upgrade head` and exits           |
| `prod`             | Runs `fastapi run` with configurable workers   |

To build the production image:

```bash
docker build --target prod -t myapp-api:1.0.0 -f backend/Dockerfile backend/
```

To run a one-off migration, build the `migrate` image and run it:

```bash
docker build --target migrate -t myapp-migrate:1.0.0 -f backend/Dockerfile backend/

docker run --rm \
    --env-file backend/.env.production \
    -e CONFIRM_PRODUCTION_MIGRATION=yes \
    myapp-migrate:1.0.0
```

The `prod` stage's `CMD` is:

```dockerfile
CMD ["sh", "-c", "fastapi run interfaces/main.py --host 0.0.0.0 --port 8000 --workers $WORKERS"]
```

`fastapi run` is FastAPI's production-friendly equivalent to `uvicorn` — it sets sane defaults (no `--reload`, properly configured logging, etc.) and is what the framework itself recommends. Override the worker count with `WORKERS` (defaults to 1):

```bash
docker run -d \
    --env-file .env.production \
    -e WORKERS=4 \
    -p 8000:8000 \
    myapp-api:1.0.0
```

### Picking a Worker Count

Rough rule: `2 × CPU cores + 1` for I/O-bound workloads, fewer for CPU-bound. Each worker is a separate process; they don't share memory. Caches and DB pools are per-worker — bring `DATABASE_POOL_SIZE` down if you're scaling workers up.

For most APIs, **don't reach for gunicorn**. `fastapi run` (which wraps uvicorn) handles process management fine. Add a process supervisor (Kubernetes, ECS, systemd, supervisord) at the orchestration layer.

## Running the Background Worker

In production, run a separate worker container/service:

```bash
docker run -d \
    --env-file .env.production \
    --target base \
    myapp-api:1.0.0 \
    sh -c "taskiq worker infrastructure.taskiq.worker:default_broker --workers 4"
```

In Kubernetes / ECS, that's a separate `Deployment` / `Service` with its own scaling. The worker doesn't accept HTTP traffic — it only consumes from the broker.

Tune via:

- `--workers <N>` — process count
- `TASKIQ_WORKER_CONCURRENCY` — async tasks per process
- `TASKIQ_MAX_TASKS_PER_WORKER` — recycle a worker after N tasks (defaults to 1000) to bound memory leaks

See [Background Tasks](background-tasks/index.md) for the full Taskiq setup.

## Database Migrations in Production

The migration env (`backend/migrations/env.py`) calls `validate_production_migration` at the start of every Alembic run. In production:

```bash
# Will FAIL — refuses to run without confirmation
CONFIRM_PRODUCTION_MIGRATION=  alembic upgrade head

# OK — explicitly confirmed
CONFIRM_PRODUCTION_MIGRATION=yes alembic upgrade head
```

This is intentional: `alembic upgrade head` should not be a routine boot-time command. Run migrations as a deliberate step in your deployment pipeline:

1. Build the new image
2. Build & run the `migrate` image with `CONFIRM_PRODUCTION_MIGRATION=yes`
3. **Then** roll out the API container

If your pipeline runs migrations after rollout, you can briefly serve a new code version against an old schema. Don't do that.

For zero-downtime deploys, do schema changes in two phases — see [Database → Migrations](database/migrations.md) for the expand/contract pattern.

## TLS, Reverse Proxy, and CORS

The boilerplate doesn't terminate TLS — that's your reverse proxy's job (Nginx, Caddy, ALB, Cloud Run's built-in TLS, etc.). Common deployment shapes:

```text
[Client] → HTTPS → [Reverse Proxy] → HTTP → [API container]
                                  → HTTP → [API container]
                                  → HTTP → [API container]
```

The proxy must:

- Forward `X-Forwarded-Proto: https` and `X-Forwarded-For: <client_ip>` (FastAPI / Starlette respect these by default)
- Pass through cookies (`Set-Cookie`) untouched
- Set `Host` correctly so the API's URL building works

`CORS_ORIGINS` should list your **frontend** origins, not the API origin. Wildcard (`*`) is incompatible with credentialed requests anyway — the validator warns on it for a reason.

## Logging in Production

Use JSON log output for ingestion into your log aggregator:

```env
LOG_LEVEL=INFO
LOG_FORMAT=json
```

The boilerplate's logger (`infrastructure/logging/`) attaches a correlation ID per request — it appears in every log line for that request, including downstream Taskiq tasks if you propagate it. Useful for tying together "user X reported error Y" with the actual server-side trace.

For lower-noise production logs:

- `LOG_LEVEL=INFO` is the right default. `WARNING` skips request logs, which makes incident debugging harder.
- Sample low-information lines (health-check polls, etc.) at the proxy or aggregator, not in the app.

For OpenTelemetry / APM integration, hook into the FastAPI app at startup — there's no built-in hook in the boilerplate.

## Health and Readiness

The boilerplate ships a `GET /api/v1/health` endpoint. Use it as your liveness probe:

```yaml
# Kubernetes / Docker probe
livenessProbe:
  httpGet:
    path: /api/v1/health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
```

For a **readiness** probe (does the app actually have working DB / Redis connections?), the built-in health check is too thin — it returns 200 immediately. If you want strict readiness, add a richer endpoint that probes the database and cache:

```python
@router.get("/ready")
async def ready(db: Annotated[AsyncSession, Depends(async_session)]) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    await cache_get(key="readiness_probe")  # short-circuit; we don't care about value
    return {"status": "ready"}
```

Drop it into a private health-only router that's not gated by the rate limiter.

## Hardening Checklist

Before shipping:

- [ ] `ENVIRONMENT=production` in the runtime
- [ ] `SECRET_KEY` is fresh, > 32 chars, never seen anywhere else
- [ ] `POSTGRES_PASSWORD` is unique and pulled from a secrets manager
- [ ] `DEBUG=false` (validator warns otherwise)
- [ ] `CORS_ORIGINS` lists only your frontend origins; no `*`
- [ ] `OPENAPI_URL=` (empty) — `/docs` and `/redoc` are not exposed
- [ ] `SESSION_SECURE_COOKIES=true` and you're terminating TLS at a proxy
- [ ] `CSRF_ENABLED=true`
- [ ] All Redis instances have `*_REDIS_PASSWORD` set
- [ ] `ADMIN_ENABLED=false` (or restricted at the network layer)
- [ ] Database migrations run via the `migrate` Dockerfile stage with `CONFIRM_PRODUCTION_MIGRATION=yes`
- [ ] `CREATE_TABLES_ON_STARTUP=false`
- [ ] Pre-commit and CI are running on every PR (lint, mypy, tests)
- [ ] Backups configured for the production database and Redis (if you're using Redis for sessions / state you can't lose)
- [ ] Monitoring set up: error rates, latency p95/p99, DB connection saturation, queue depth, Redis memory

## Scaling Considerations

### API instances

Horizontal scaling is straightforward — add more `prod` containers behind your load balancer. Sessions are stored in Redis (when `SESSION_BACKEND=redis`), so any instance can serve any user.

If you're stuck on `SESSION_BACKEND=memory`, you can't horizontally scale safely: each instance has its own session table. Switch backends before scaling.

### Database

Watch `database_pool_size × api_workers + worker_concurrency × taskiq_workers` against your Postgres `max_connections`. Common pitfall: 4 API workers × 10 pool size = 40 connections per API replica, easy to blow past 100 connection cap with two replicas + Taskiq.

Use a connection pooler (PgBouncer, RDS Proxy) at scale. The boilerplate's `DATABASE_URL` accepts a pooler endpoint identically.

### Redis

The defaults use four separate DB numbers (`CACHE_REDIS_DB=0`, `SESSION_REDIS_DB=1`, `RATE_LIMITER_REDIS_DB=1`, `TASKIQ_REDIS_DB=3`) on the **same** Redis instance. Fine for small deployments. At scale, split sessions and the cache onto different Redis clusters — sessions are small and durability-sensitive; the cache is large, eviction-tolerant, and high-traffic. Mixing them puts your sessions at risk during cache memory pressure.

### Taskiq workers

Worker scaling is independent of API scaling. If your tasks become a bottleneck, scale the worker `Deployment` without touching the API.

## Common Production Issues

### "App fails to boot with `ProductionSecurityError`"

Read the message — it tells you which check failed. Don't bypass it; fix the underlying config.

### "Sessions invalidate after every deploy"

You're on `SESSION_BACKEND=memory`. Switch to `redis` (or `memcached`) and add the relevant `*_REDIS_*` env vars.

### "Sudden burst of 429s after a config change"

Check that your rate-limit rule rows still match the routes. After path renames or sanitization rule changes, the lookup may miss and apply the (often tighter) `DEFAULT_RATE_LIMIT_LIMIT` instead.

### "Cache backend not available" warnings under load

Pool exhaustion. Bump `CACHE_REDIS_POOL_SIZE` (default 10), check Redis memory pressure, look for connection leaks in your application code.

### "Tasks queue but no worker picks them up"

The worker process isn't running, isn't pointed at the same Redis, or hasn't imported the task module. See [Background Tasks → Troubleshooting](background-tasks/index.md#troubleshooting).

### "404 on `/admin` after deploy"

`ADMIN_ENABLED=false`. Either enable it (and lock it down at the network layer) or run admin tasks through scripts.

## Key Files

| Component                         | Location                                                          |
|-----------------------------------|-------------------------------------------------------------------|
| Production validator              | `backend/src/infrastructure/security/production_validator.py`     |
| Migration validator               | `backend/migrations/env.py:validate_production_migration`         |
| Multi-stage Dockerfile            | `backend/Dockerfile`                                              |
| Settings                          | `backend/src/infrastructure/config/settings.py`                   |
| App factory / lifespan            | `backend/src/infrastructure/app_factory.py`                       |

## Next Steps

- **[Configuration → Environment-Specific](configuration/environment-specific.md)** — per-environment env-var matrix
- **[Database → Migrations](database/migrations.md)** — zero-downtime schema-change patterns
- **[Authentication → Sessions](authentication/sessions.md)** — production session configuration
- **[Testing](testing.md)** — the test setup that ships with the boilerplate
