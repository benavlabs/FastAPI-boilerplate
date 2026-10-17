# Docker Setup

This page walks through running the boilerplate in containers. The Python project lives at
`backend/`, and the image builds from the repository root: it needs the workspace's
`pyproject.toml`, `uv.lock` and `cli/pyproject.toml` as well as `backend/`. You run
`docker compose` from the repository root too.

!!! info "The compose file is generated, not shipped"
    No compose file is committed. `bp deploy generate local` writes one at the repository root,
    where it is gitignored, so regenerating it never conflicts with the repo. `prod` and `nginx`
    write the other two stacks. See [CLI commands](../../cli/commands.md#bp-deploy-generate).

## Quick Start

```bash
cp backend/.env.example backend/.env
# edit backend/.env (set SECRET_KEY, change default DB password, etc.)
uv run --no-sync bp deploy generate local
docker compose up --build
```

## Dockerfile Architecture

`backend/Dockerfile` uses **four stages** built from `python:3.11-slim`:

| Stage | Purpose |
|-------|---------|
| `requirements-stage` | Exports pinned requirements from `uv.lock` into `requirements-prod.txt` and `requirements-dev.txt`. Uses the official `astral-sh/uv` image to do this reliably. |
| `base` | Installs system deps (gcc), production Python deps, and copies `src/` into the image. Sets `PYTHONPATH=/app:/app/src`. |
| `dev` | Adds dev requirements and `tests/`, runs as a non-root `appuser`, starts with `fastapi dev interfaces/main.py --host 0.0.0.0 --port 8000`. |
| `migrate` | Adds `migrations/` and `alembic.ini`. Default command is `alembic upgrade head`. Useful as a one-off job before the prod app starts. |
| `prod` | Same as base, runs as non-root, starts with `fastapi run interfaces/main.py --host 0.0.0.0 --port 8000 --workers $WORKERS` (defaults to 1). |

You select a stage with `--target` when building. The context is the repository root, because the Dockerfile copies `pyproject.toml`, `uv.lock`, `backend/` and `cli/pyproject.toml` from there:

```bash
docker build --target dev -t fastapi-boilerplate:dev -f backend/Dockerfile .
docker build --target prod -t fastapi-boilerplate:prod -f backend/Dockerfile .
docker build --target migrate -t fastapi-boilerplate:migrate -f backend/Dockerfile .
```

## What `bp deploy generate local` Writes

Four services, named `api`, `worker`, `postgres` and `redis`, with the API and the worker built
from the `dev` stage and the source mounted for reload:

```yaml
services:
  api:
    build:
      context: .
      dockerfile: backend/Dockerfile
      target: dev
    env_file:
      - ./backend/.env
    environment:
      POSTGRES_SERVER: postgres
      CACHE_REDIS_HOST: redis
      RATE_LIMITER_REDIS_HOST: redis
      TASKIQ_REDIS_HOST: redis
    volumes:
      - ./backend/src:/app/src
      - ./backend/tests:/app/tests
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
```

`worker` is the same image running `taskiq worker infrastructure.taskiq.worker:default_broker
--reload`; `postgres` and `redis` carry healthchecks that the other two wait on, and keep their
data in the named volumes `postgres-data` and `redis-data`. `--api-port` moves the published port,
and `--dry-run` prints the file without writing it.

### Matching `.env` for Compose

When the app talks to the other services in the Compose network, it uses **service names** as hostnames:

```env
# In backend/.env
POSTGRES_SERVER=postgres
CACHE_REDIS_HOST=redis
RATE_LIMITER_REDIS_HOST=redis
TASKIQ_REDIS_HOST=redis
```

If you also use the host machine to reach Postgres/Redis directly (e.g. for a local dev tool), keep `localhost` working by exposing those ports as the example does (`127.0.0.1:5432:5432`, `127.0.0.1:6379:6379`). The `127.0.0.1:` prefix keeps a password-less dev database off the rest of the network.

## Service Reference

### `api` — FastAPI Application

Built from the `dev` Dockerfile stage. Runs `fastapi dev`, which auto-reloads on code changes. The
volume mount on `./backend/src` makes the reload pick up your edits live.

For production, generate the `prod` or `nginx` stack instead of editing this one: both build the
`prod` stage, drop the mounts and run `fastapi run` with `--workers`.

### `worker` — Taskiq Worker

The same image, running `taskiq worker infrastructure.taskiq.worker:default_broker --reload`. Scale
it with `docker compose up --scale worker=3`.

### `postgres` — PostgreSQL 16

`postgres:16-alpine`. Reads `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` from
`backend/.env`, and persists data in the named volume `postgres-data`.

### `redis` — Redis 7

Used for cache (`CACHE_REDIS_DB=0`), rate limiting (`RATE_LIMITER_REDIS_DB=1`), sessions (`SESSION_REDIS_DB=2`), and the Taskiq broker (`TASKIQ_REDIS_DB=3`). The boilerplate uses different DB numbers so they don't interfere.

## Optional Services

Add these to the generated `docker-compose.yml` as needed. A regenerated file loses them, so keep
your additions in a `docker-compose.override.yml` instead if you expect to regenerate.

### Migrations Job

Run Alembic migrations before the app starts:

```yaml
  migrate:
    build:
      context: .
      dockerfile: backend/Dockerfile
      target: migrate
    env_file:
      - ./backend/.env
    environment:
      POSTGRES_SERVER: postgres
    depends_on:
      postgres:
        condition: service_healthy
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
      dockerfile: backend/Dockerfile
      target: dev
    env_file:
      - ./backend/.env
    environment:
      POSTGRES_SERVER: postgres
    command: python -m scripts.setup_initial_data
    depends_on:
      postgres:
        condition: service_healthy
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
      - postgres
```

Visit <http://localhost:5050>, log in, and add a server with hostname `postgres`, port `5432`, user `postgres` (or whatever you set in `backend/.env`).

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
CACHE_MEMCACHED_HOST=memcached
```

The rate limiter is always Redis-backed, so it still needs the `redis` service.

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
# from the repository root, where the generated compose file lives

# Bring everything up (foreground, attached logs)
docker compose up

# Detached
docker compose up -d

# Rebuild after dependency changes
docker compose up --build

# Logs for a specific service
docker compose logs -f api

# Open a shell inside the app container
docker compose exec api bash

# Run a one-off command
docker compose exec api uv run --no-sync alembic upgrade head
docker compose exec postgres psql -U postgres
docker compose exec redis redis-cli

# Stop everything
docker compose down

# Stop and wipe volumes (⚠️ deletes data)
docker compose down -v
```

## Production-Style Setup

For a more production-like local stack:

1. **Generate the `prod` stack**: `bp deploy generate prod` builds the `prod` stage, drops the
   source mounts and runs `fastapi run --workers`.
2. **Run migrations as a separate job** (the `migrate` service above) before the app starts.
3. **Set the worker count**: `bp deploy generate prod --workers 4`, or `WORKERS=4` in
   `backend/.env` (the `prod` command reads it).
5. **Add a reverse proxy** if you need TLS — Caddy or Traefik are simpler to configure than nginx for single-host setups.

## Troubleshooting

### Container won't start

```bash
docker compose logs api
docker compose build --no-cache api
```

### Database connection refused

```bash
# Is the database service up?
docker compose ps postgres

# Can the api container resolve "postgres"?
docker compose exec api python -c "import socket; print(socket.gethostbyname('postgres'))"

# Inspect its logs
docker compose logs postgres
```

### Code changes not picking up

Make sure you have the `./backend/src:/app/src` volume mount in the `api` service, and that `target: dev` is set (the `dev` stage uses `fastapi dev` which has reload enabled). The `prod` stage does **not** auto-reload.

### Port already in use

```bash
lsof -i :8000
# or change the host-side port in compose:
ports:
  - "8080:8000"
```

### Resetting everything

```bash
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
