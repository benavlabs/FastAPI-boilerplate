# Docker Setup

This page walks through running the boilerplate in containers. The Python project lives at `backend/`, so all Docker operations happen from there.

!!! info "docker-compose.yml status"
    The repository ships a `backend/Dockerfile` (multi-stage). A canonical `backend/docker-compose.yml` is on the way — until then, the **Recommended Compose File** below is what to drop in at `backend/docker-compose.yml` to get the `docker compose up` flow running.

## Quick Start

```bash
cd backend
cp .env.example .env
# edit .env (set SECRET_KEY, change default DB password, etc.)
docker compose up
```

## Dockerfile Architecture

`backend/Dockerfile` uses **four stages** built from `python:3.11-slim`:

| Stage | Purpose |
|-------|---------|
| `requirements-stage` | Exports pinned requirements from `uv.lock` into `requirements-prod.txt` and `requirements-dev.txt`. Uses the official `astral-sh/uv` image to do this reliably. |
| `base` | Installs system deps (gcc), production Python deps, and copies `src/` into the image. Sets `PYTHONPATH=/app/src`. |
| `dev` | Adds dev requirements and `tests/`, runs as a non-root `appuser`, starts with `fastapi dev interfaces/main.py --host 0.0.0.0 --port 8000`. |
| `migrate` | Adds `migrations/` and `alembic.ini`. Default command is `alembic upgrade head`. Useful as a one-off job before the prod app starts. |
| `prod` | Same as base, runs as non-root, starts with `fastapi run interfaces/main.py --host 0.0.0.0 --port 8000 --workers $WORKERS` (defaults to 1). |

You select a stage with `--target` when building:

```bash
docker build --target dev -t fastapi-boilerplate:dev backend
docker build --target prod -t fastapi-boilerplate:prod backend
docker build --target migrate -t fastapi-boilerplate:migrate backend
```

## Recommended Compose File

Save this as `backend/docker-compose.yml`. It brings up Postgres, Redis, and the FastAPI app in dev mode:

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
      target: dev
    env_file:
      - .env
    ports:
      - "8000:8000"
    volumes:
      - ./src:/app/src       # live code reload
      - ./tests:/app/src/tests
    depends_on:
      - db
      - redis

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-postgres}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    ports:
      - "6379:6379"

volumes:
  postgres-data:
  redis-data:
```

### Matching `.env` for Compose

When the app talks to the other services in the Compose network, it uses **service names** as hostnames:

```env
# In backend/.env
POSTGRES_SERVER=db
CACHE_REDIS_HOST=redis
RATE_LIMITER_REDIS_HOST=redis
TASKIQ_REDIS_HOST=redis
```

If you also use the host machine to reach Postgres/Redis directly (e.g. for a local dev tool), keep `localhost` working by exposing those ports as the example does (`5432:5432`, `6379:6379`).

## Service Reference

### `app` — FastAPI Application

Built from the `dev` Dockerfile stage. Runs `fastapi dev`, which auto-reloads on code changes. The volume mount on `./src` makes the reload pick up your edits live.

To switch to production mode, change `target: dev` → `target: prod` and drop the volume mounts.

### `db` — PostgreSQL 17

Postgres 17 (alpine for size). Reads `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` from the environment, and persists data in the named volume `postgres-data`.

### `redis` — Redis 7

Used for cache (`CACHE_REDIS_DB=0`), rate limiting (`RATE_LIMITER_REDIS_DB=1`), sessions, and the Taskiq broker (`TASKIQ_REDIS_DB=3`). The boilerplate uses different DB numbers so they don't interfere.

## Optional Services

Add these to your `docker-compose.yml` as needed.

### Taskiq Worker

To process background tasks, add a worker service:

```yaml
  worker:
    build:
      context: .
      dockerfile: Dockerfile
      target: dev
    env_file:
      - .env
    command: taskiq worker infrastructure.taskiq.worker:default_broker
    volumes:
      - ./src:/app/src
    depends_on:
      - db
      - redis
```

Scale workers with `docker compose up --scale worker=3`.

### Migrations Job

Run Alembic migrations before the app starts:

```yaml
  migrate:
    build:
      context: .
      dockerfile: Dockerfile
      target: migrate
    env_file:
      - .env
    depends_on:
      - db
```

```bash
docker compose run --rm migrate
```

### Initial Setup Job

Create the first admin user and default tier on a fresh DB:

```yaml
  setup:
    build:
      context: .
      dockerfile: Dockerfile
      target: dev
    env_file:
      - .env
    command: python -m scripts.setup_initial_data
    depends_on:
      - db
```

```bash
docker compose run --rm setup
```

### pgAdmin

If you want a web UI for the database, add:

```yaml
  pgadmin:
    image: dpage/pgadmin4:latest
    restart: unless-stopped
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@example.com
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - db
```

Visit <http://localhost:5050>, log in, and add a server with hostname `db`, port `5432`, user `postgres` (or whatever you set in `.env`).

### Memcached (alternative cache backend)

If you prefer Memcached over Redis:

```yaml
  memcached:
    image: memcached:1.6-alpine
    ports:
      - "11211:11211"
```

And in `.env`:

```env
CACHE_BACKEND=memcached
RATE_LIMITER_BACKEND=memcached
CACHE_MEMCACHED_HOST=memcached
RATE_LIMITER_MEMCACHED_HOST=memcached
```

### RabbitMQ (alternative Taskiq broker)

```yaml
  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    environment:
      RABBITMQ_DEFAULT_USER: ${TASKIQ_RABBITMQ_USER:-guest}
      RABBITMQ_DEFAULT_PASS: ${TASKIQ_RABBITMQ_PASSWORD:-guest}
    ports:
      - "5672:5672"
      - "15672:15672"   # management UI
```

In `.env`:

```env
TASKIQ_BROKER_TYPE=rabbitmq
TASKIQ_RABBITMQ_HOST=rabbitmq
```

## Common Commands

```bash
cd backend

# Bring everything up (foreground, attached logs)
docker compose up

# Detached
docker compose up -d

# Rebuild after dependency changes
docker compose up --build

# Logs for a specific service
docker compose logs -f app

# Open a shell inside the app container
docker compose exec app bash

# Run a one-off command
docker compose exec app uv run alembic upgrade head
docker compose exec db psql -U postgres
docker compose exec redis redis-cli

# Stop everything
docker compose down

# Stop and wipe volumes (⚠️ deletes data)
docker compose down -v
```

## Production-Style Setup

For a more production-like local stack:

1. **Use the `prod` stage**: change `target: dev` to `target: prod` in the `app` service.
2. **Drop dev volume mounts**: remove `./src:/app/src` so the image is the source of truth.
3. **Run migrations as a separate job** (the `migrate` service above) before the app starts.
4. **Bump worker count**: set `WORKERS=4` in `.env` (the `prod` command reads it).
5. **Add a reverse proxy** if you need TLS — Caddy or Traefik are simpler to configure than nginx for single-host setups.

## Troubleshooting

### Container won't start

```bash
docker compose logs app
docker compose build --no-cache app
```

### Database connection refused

```bash
# Is the db service up?
docker compose ps db

# Can the app container resolve "db"?
docker compose exec app python -c "import socket; print(socket.gethostbyname('db'))"

# Inspect db logs
docker compose logs db
```

### Code changes not picking up

Make sure you have the `./src:/app/src` volume mount in the `app` service, and that `target: dev` is set (the `dev` stage uses `fastapi dev` which has reload enabled). The `prod` stage does **not** auto-reload.

### Port already in use

```bash
lsof -i :8000
# or change the host-side port in compose:
ports:
  - "8080:8000"
```

### Resetting everything

```bash
cd backend
docker compose down -v        # wipes volumes
docker compose build --no-cache
docker compose up
```

## Best Practices

### Development
- Use `target: dev` for live reload
- Mount `./src` as a volume so edits don't require rebuilds
- Expose Postgres/Redis ports for easy local debugging
- Keep `.env` out of version control (it's already in `.gitignore`)

### Production
- Use `target: prod` and remove dev volume mounts
- Run the `migrate` stage as a separate job before launching the app
- Set `ENVIRONMENT=production` to enable the security validator
- Run as the non-root `appuser` (already set up in the Dockerfile)
- Pin image tags (`postgres:16-alpine`, not `postgres:latest`)

### Security
- Containers run as non-root in dev/prod stages
- Don't expose the Postgres/Redis ports to public networks in production
- Set strong `POSTGRES_PASSWORD`, Redis passwords (`CACHE_REDIS_PASSWORD`, etc.) and `SECRET_KEY` before deploying

## See Also

- **[Environment Variables](environment-variables.md)** — Full env var reference
- **[Settings Classes](settings-classes.md)** — How env vars become Python settings
- **[Production](../production.md)** — Production deployment guide
