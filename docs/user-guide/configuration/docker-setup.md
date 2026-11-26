# Docker Setup

This page walks through running the boilerplate in containers. The Python project lives at
`backend/`, and the image builds from the repository root: it needs the workspace's
`pyproject.toml` and `uv.lock` as well as `backend/`. You run `docker compose` from the
repository root too.

!!! info "The compose file is generated, not shipped"
    No compose file is committed. `fastro make deploy local` writes one at the repository root,
    where it is gitignored, so regenerating it never conflicts with the repo. `prod` and `nginx`
    write the other two stacks. See [`fastro make deploy`](../fastro.md#writing-the-compose-files-fastro-make-deploy).

## Quick Start

```bash
cp backend/.env.example backend/.env
# edit backend/.env (set SECRET_KEY, change default DB password, etc.)
uv run --no-sync fastro make deploy local
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

You select a stage with `--target` when building. The context is the repository root, because the Dockerfile copies `pyproject.toml`, `uv.lock` and `backend/` from there:

```bash
docker build --target dev -t fastapi-boilerplate:dev -f backend/Dockerfile .
docker build --target prod -t fastapi-boilerplate:prod -f backend/Dockerfile .
docker build --target migrate -t fastapi-boilerplate:migrate -f backend/Dockerfile .
```

## What `fastro make deploy local` Writes

For a project with the taskiq feature, the services are `api`, `worker`, `scheduler`, `postgres` and
`redis`, with the API, the worker and the scheduler built from the `dev` stage and the source
mounted. A project without taskiq gets no `worker` or `scheduler`:

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

`worker` is the same image running `taskiq worker src.infrastructure.taskiq.worker:default_broker
--reload`, and `scheduler` the same image running
`taskiq scheduler src.infrastructure.taskiq.scheduler:scheduler`. `postgres` and `redis` carry
healthchecks that the others wait on, and keep their data in the named volumes `postgres-data` and
`redis-data`. `--api-port` moves the published port,
and `--dry-run` prints the file without writing it. A choice that needs a service of its own adds
it, in all three stacks: `memcached` with `cache.backend=memcached` and `rabbitmq` with
`taskiq.broker=rabbitmq` (see the [Service Reference](#service-reference)).

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

### `api`: FastAPI Application

Built from the `dev` Dockerfile stage. Runs `fastapi dev`, which auto-reloads on code changes. The
volume mount on `./backend/src` makes the reload pick up your edits live.

For production, generate the `prod` or `nginx` stack instead of editing this one: both build the
`prod` stage, drop the mounts and run `fastapi run` with `--workers`.

### `worker`: Taskiq Worker

The same image, running `taskiq worker src.infrastructure.taskiq.worker:default_broker --reload`.
Scale it with `docker compose up --scale worker=3`.

### `scheduler`: Taskiq Scheduler

The same image, running `taskiq scheduler src.infrastructure.taskiq.scheduler:scheduler`, which
enqueues the scheduled tasks and the delayed retries when they are due. Run exactly one: each
scheduler fires every schedule it finds, so scale the worker instead (see
[Scheduled Tasks](../background-tasks/index.md#scheduled-tasks)).

### `postgres`: PostgreSQL 16

`postgres:16-alpine`. Reads `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` from
`backend/.env`, and persists data in the named volume `postgres-data`.

### `redis`: Redis 7

Used for cache (`CACHE_REDIS_DB=0`), rate limiting (`RATE_LIMITER_REDIS_DB=1`), sessions (`SESSION_REDIS_DB=2`), and the Taskiq broker (`TASKIQ_REDIS_DB=3`). The boilerplate uses different DB numbers so they don't interfere.

In the `prod` and `nginx` stacks it requires the password the app connects with, the one
`CACHE_REDIS_PASSWORD`, `RATE_LIMITER_REDIS_PASSWORD`, `TASKIQ_REDIS_PASSWORD` or
`SESSION_REDIS_PASSWORD` sets in `backend/.env`. The cache, the rate limiter and the broker always
connect to this one Redis, so give them one value: it refuses to start when two differ, and runs
without a password when none is set. Sessions connect to it too unless `SESSION_REDIS_URL` is set
or `SESSION_REDIS_HOST` names another host, and only then is their password left out. The `local`
stack runs it without one.

It speaks plaintext, which is by design: its traffic stays on the compose network. Leave
`*_REDIS_SSL=false` for it, even where the production examples set them to true, since those run
on a Redis elsewhere. The [production check](../production.md#warnings-logged-app-starts) still
warns that it doesn't use TLS, since its host `redis` is neither `localhost` nor `127.0.0.1`. A
Redis on another host, or a managed one, is one to reach over TLS, with `*_REDIS_SSL=true`.

### `memcached`: Memcached 1.6

Only in a project generated with `cache.backend=memcached`. `memcached:1.6-alpine`, with a
healthcheck the app containers wait on; the file sets `CACHE_MEMCACHED_HOST=memcached` on each of
them. It holds the cache alone: the rate limiter's Memcached backend was removed, and
[Rate Limiting](../rate-limiting/index.md#configuration) says where its counters live.

### `rabbitmq`: RabbitMQ 4

Only in a project generated with `taskiq.broker=rabbitmq`. `rabbitmq:4-alpine`, started with the
user, password and vhost that `TASKIQ_RABBITMQ_USER`, `TASKIQ_RABBITMQ_PASSWORD` and
`TASKIQ_RABBITMQ_VHOST` set in `backend/.env`, so the app logs in as the user the broker creates.
The file sets `TASKIQ_RABBITMQ_HOST=rabbitmq` on the app containers, which wait on its healthcheck,
and keeps the queues in the named volume `rabbitmq-data`. The image creates that user only when
`rabbitmq-data` is empty: after changing them in `backend/.env`, change the user with `rabbitmqctl`
inside the container, or start over with `docker compose down -v`, which deletes the queued tasks.

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

1. **Generate the `prod` stack**: `fastro make deploy prod` builds the `prod` stage, drops the
   source mounts and runs `fastapi run --workers`.
2. **Run migrations as a separate job** (the `migrate` service above) before the app starts.
3. **Set the worker count**: `fastro make deploy prod --workers 4`, or `WORKERS=4` in
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
