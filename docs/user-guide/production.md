# Production Deployment

This page is the production hardening checklist for a FastAPI-boilerplate deployment. It covers the boilerplate's built-in production validators, env-var hygiene, the multi-stage Dockerfile that ships, and the operational decisions you'll make once.

## The Production Validator

When `ENVIRONMENT=production`, `infrastructure/security/production_validator.py` runs at startup and refuses to boot the app on critical issues. Two tiers:

### Critical (raises `ProductionSecurityError`, app exits)

The app **will not start** if any of these is true:

- **`SECRET_KEY` reads as something other than random.** Refused when it is empty or under 32
  characters, or when one of these covers most of its length: a placeholder or hand-written word
  (`password`, `secret`, `test`, `dev`, `default`, …), a short block written out again
  (`prodprodprod…`), a walk across neighbouring keys (`qwertyuiop…`, `1qaz2wsx…`), or words anyone
  would recognise (`MyCompanyApiSigningKeyForProd2026`, `thisismysupersecurekeyforthisapp`). Each of
  those is measured as a share of the whole value, so a generated key that happens to spell a word
  still passes. Two rules are absolute: a run of eight consecutive code points, and under 64 bits
  of entropy. The tests sweep 100,000 keys of each shape a generator produces — the hex keys
  `bp env gen-secret` prints (`secrets.token_hex(16/32)`) and `secrets.token_urlsafe(24/32)` keys
  from whatever else you might use — from a fixed seed, and none of the 400,000 is refused. A
  random key can still trip a rule: one hex key in 12.6 million runs through eight consecutive
  digits, and a `token_urlsafe` key walks the keyboard at around one in ten million. Run inside a
  project, `bp env gen-secret` checks each draw against those rules and draws again while they
  would refuse it.
- **The database password is `postgres`** (the well-known default). Attackers try this first.
- **The database password is empty.** Database is unprotected.
- **The admin panel is enabled without credentials** (`ADMIN_ENABLED=true` with `ADMIN_USERNAME` or `ADMIN_PASSWORD` unset).
- **`CORS_ORIGINS` contains `*`.** Any website can call the API from a user's browser. The app drops `CORS_ALLOW_CREDENTIALS` while `*` is listed, so it answers `Access-Control-Allow-Origin: *` with no `Access-Control-Allow-Credentials`: a page on another origin cannot read a response to a call it made with the user's cookies. The call itself is still sent when it needs no preflight, cookie included wherever `SameSite` allows it, so a `*` origin neither protects the endpoint nor serves a logged-in frontend.

The password checked is the one actually used to connect: when `DATABASE_URL` is set it's read out of that URL, otherwise it's `POSTGRES_PASSWORD`. A `DATABASE_URL` with no password at all (IAM or certificate authentication) is a warning rather than an error, since it can't be verified from here.

### Warnings (logged, app starts)

These don't block startup but you should fix them before the app sees real traffic:

- **Redis without a password** (`CACHE_REDIS_PASSWORD` or `RATE_LIMITER_REDIS_PASSWORD` unset, or a `SESSION_REDIS_URL` without one)
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
SESSION_BACKEND=redis                  # redis | memory, on the cache Redis unless SESSION_REDIS_URL is set
SESSION_SECURE_COOKIES=true            # required when serving over HTTPS
CSRF_ENABLED=true
TRUSTED_PROXY_HOPS=1                    # set to the number of proxies in front of the app
FORWARDED_ALLOW_IPS=<proxy-subnet>     # which peers uvicorn takes forwarded headers from

# Rate limiting (Redis-backed, provided by crudauth)
RATE_LIMITER_ENABLED=true
RATE_LIMITER_REDIS_HOST=<redis-host>
RATE_LIMITER_REDIS_PASSWORD=<redis-password>

# Taskiq
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
docker build --target prod -t myapp-api:1.0.0 -f backend/Dockerfile .
```

To run a one-off migration, build the `migrate` image and run it:

```bash
docker build --target migrate -t myapp-migrate:1.0.0 -f backend/Dockerfile .

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

Rough rule: `2 × CPU cores + 1` for I/O-bound workloads, fewer for CPU-bound. Each worker is a separate process; they don't share memory. Caches and DB pools are per-worker — bring `POSTGRES_POOL_SIZE` down if you're scaling workers up.

For most APIs, **don't reach for gunicorn**. `fastapi run` (which wraps uvicorn) handles process management fine. Add a process supervisor (Kubernetes, ECS, systemd, supervisord) at the orchestration layer.

## Running the Background Worker

In production, run a separate worker container/service:

```bash
docker run -d \
    --env-file .env.production \
    --target base \
    myapp-api:1.0.0 \
    sh -c "taskiq worker src.infrastructure.taskiq.worker:default_broker --workers 4"
```

In Kubernetes / ECS, that's a separate `Deployment` / `Service` with its own scaling. The worker doesn't accept HTTP traffic — it only consumes from the broker.

Tune via:

- `--workers <N>` — process count
- taskiq's `--max-async-tasks <N>` — async tasks per process

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

Set `TRUSTED_PROXY_HOPS` to the number of reverse proxies you've put in front of the app (1 for a single nginx/Caddy, 2 if Cloudflare is also in front). crudauth uses it to read the real client IP from the last trusted hop of `X-Forwarded-For` when applying login lockout — otherwise every request would appear to come from the proxy and the lockout would key on a single IP.

Set `FORWARDED_ALLOW_IPS` to your proxy's address or subnet. **uvicorn** reads it from its own process environment, not through the app's settings, and it decides what `request.client` and the access logs report. A wildcard makes uvicorn take the *leftmost* `X-Forwarded-For` entry, which is whatever the client sent, so any client can claim any address and say its request arrived over HTTPS. Named a subnet, uvicorn skips the entries from that subnet and reads the last one outside it. The generated nginx vhost also replaces `X-Forwarded-For` with the address nginx saw, so there is only ever one entry to read. The generated stack puts the containers on a fixed subnet and sets this to that CIDR; `bp deploy generate nginx --internal-subnet 10.20.30.0/24` changes both together, and refuses host bits, a wildcard, or a range wider than `/8` (IPv4) or `/48` (IPv6).

!!! warning "nginx is the only hop in the generated stack"

    Replacing `X-Forwarded-For` discards whatever arrived in it. That is what you want when nginx
    is the first thing a client reaches, and wrong as soon as something else sits in front of it —
    a cloud load balancer, Cloudflare, another nginx. In that setup the client address arrives in
    the header, so three settings change together:

    - edit the generated `nginx/default.conf` back to
      `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`, so the entries from upstream
      survive;
    - raise `TRUSTED_PROXY_HOPS` to the number of proxies in front of the app, so crudauth skips
      their entries and reads the client's;
    - add the upstream proxy's address or subnet to `FORWARDED_ALLOW_IPS`, alongside the compose
      network. uvicorn trusts only the peers named there, so with the generated value alone it
      stops at the load balancer's entry and reports *that* as `request.client` and in the access
      logs. crudauth's per-IP limits stay correct either way once `TRUSTED_PROXY_HOPS` is right,
      since it counts hops from the right itself.

!!! note "Per-IP limits on Docker Desktop"

    Where Docker's userland proxy carries the connection — Docker Desktop on macOS and Windows,
    rootless Docker — nginx sees every client as the network gateway, so `$remote_addr` is the same
    address for everyone and anything keyed per IP (the login lockout, an anonymous rate limit) is
    shared across clients. On a Linux host with the bridge driver, nginx sees the real client
    addresses. Test per-IP behaviour on a Linux host, or in front of a real proxy.

`CORS_ORIGINS` should list your **frontend** origins, not the API origin. A wildcard (`*`) is incompatible with credentialed requests anyway, and the production validator refuses to start with one.

## Logging in Production

Use JSON log output for ingestion into your log aggregator:

```env
LOG_LEVEL=INFO
LOG_FORMAT=json
```

`infrastructure/logging/` ships the pieces for a correlation ID — a context variable, a `CorrelationIdFilter`, `set_correlation_id()` and `add_correlation_id_filter()` — but nothing installs them, so log lines carry no request id out of the box. Wire it up with middleware that calls `set_correlation_id()` per request and `add_correlation_id_filter()` at startup; the `structured` and `json` formats then carry the field. The catch-all error handler already logs a support id per failed request, which is what ties a user's report to a server-side trace today.

For lower-noise production logs:

- `LOG_LEVEL=INFO` is the right default. `WARNING` skips request logs, which makes incident debugging harder.
- Sample low-information lines (health-check polls, etc.) at the proxy or aggregator, not in the app.

For OpenTelemetry / APM integration, hook into the FastAPI app at startup — there's no built-in hook in the boilerplate.

## Health and Readiness

The boilerplate ships a `GET /health` endpoint, mounted on the app rather than under the API prefix. Use it as your liveness probe:

```yaml
# Kubernetes / Docker probe
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
```

For a **readiness** probe (does the app actually have working DB / Redis connections?), use `GET /health/ready`. It runs the checks the project's wiring lists, in two groups:

- `CRITICAL_READINESS_CHECKS` — the database, plus the login lockout's Redis and the session store when accounts is wired. A request can't be served without these, so one of them being unreachable answers `503` and a load balancer holds traffic back.
- `INFORMATIONAL_READINESS_CHECKS` — the cache and the task broker. No request waits on either, so an outage there is logged and the answer stays `200`.

```yaml
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

The body carries the overall status and nothing else:

```json
{ "status": "ready" }
```

A `database`, `rate_limiter` or `sessions` outage answers `503` with `{"status": "not ready"}`. Which
dependency answered what stays in the log, where a probe that found something unreachable writes a
line naming it:

```text
WARNING Readiness check cache failed: ConnectionError
WARNING Readiness: cache unavailable, which does not hold traffic back
ERROR   Readiness: database unavailable, holding traffic back
```

Each check runs with its own two-second timeout, and they all run together, so one blackholed
server can't hold the probe open. Two checks pointed at the same server are asked once - the server
is the scheme, host and port, so a cache on Redis database 0 and sessions on database 1 of one
server count as one. Probes that arrive together share one run of the checks, and its report is
reused for a couple of seconds, so a flood of probes can't take the database pool away from real
requests.

Neither health route is throttled, and both stay out of the API prefix so an API-wide rate limit or auth dependency can't take your probes down. To report on something else this project needs, contribute a `ReadinessCheck` from the feature that owns it and list it in `src/wiring/hooks.py` — under `CRITICAL_READINESS_CHECKS` when a request can't be served without it, under `INFORMATIONAL_READINESS_CHECKS` otherwise. See [Composable Features](composable-features.md).

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

Managed Postgres works the same way — point `DATABASE_URL` at the provider and leave the rest of the config alone. [Neon](database/neon.md) (serverless, scale-to-zero, database branching for preview environments) is the setup we document end to end, including the TLS parameter, pooled vs. direct endpoints, and pool tuning for a compute that suspends when idle.

### Redis

The defaults use four separate DB numbers (`CACHE_REDIS_DB=0`, `RATE_LIMITER_REDIS_DB=1`, `SESSION_REDIS_DB=2`, `TASKIQ_REDIS_DB=3`) on the **same** Redis instance. Fine for small deployments. At scale, split sessions and the cache onto different Redis clusters — sessions are small and durability-sensitive; the cache is large, eviction-tolerant, and high-traffic. Mixing them puts your sessions at risk during cache memory pressure. Sessions follow the cache's Redis connection by default; set `SESSION_REDIS_URL` (e.g. `rediss://user:password@sessions-redis:6380/0`) to give them their own instance.

The limiter's Redis (`RATE_LIMITER_REDIS_*`) is a hard dependency of logging in: the login lockout fails **closed**, so while that instance is unreachable every login is refused with `429`. Alert on it. See [Sessions → Login Lockout](authentication/sessions.md#login-lockout).

### Taskiq workers

Worker scaling is independent of API scaling. If your tasks become a bottleneck, scale the worker `Deployment` without touching the API.

## Common Production Issues

### "App fails to boot with `ProductionSecurityError`"

Read the message — it tells you which check failed. Don't bypass it; fix the underlying config.

### "Sessions invalidate after every deploy"

You're on `SESSION_BACKEND=memory`. Switch to `redis`; sessions use the cache's Redis connection, or `SESSION_REDIS_URL` when set. (Sessions support only `redis` and `memory`; memcached is not a session backend.)

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
