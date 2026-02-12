<h1 align="center"> Benav Labs FastAPI boilerplate</h1>
<p align="center" markdown=1>
  <i><b>Batteries-included FastAPI starter</b> with production-ready defaults, optional modules, and clear docs.</i>
</p>

<p align="center">
  <a href="https://benavlabs.github.io/FastAPI-boilerplate">
    <img src="docs/assets/FastAPI-boilerplate.png" alt="Purple Rocket with FastAPI Logo as its window." width="25%" height="auto">
  </a>
</p>

<p align="center">
📚 <a href="https://benavlabs.github.io/FastAPI-boilerplate/">Docs</a> · 🧠 <a href="https://deepwiki.com/benavlabs/FastAPI-boilerplate">DeepWiki</a> · 💬 <a href="https://discord.com/invite/TEmPs22gqB">Discord</a>
</p>

<p align="center">
  <a href="https://fastapi.tiangolo.com">
      <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi" alt="FastAPI">
  </a>
  <a href="https://www.postgresql.org">
      <img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL">
  </a>
  <a href="https://redis.io">
      <img src="https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=fff&style=for-the-badge" alt="Redis">
  </a>
  <a href="https://deepwiki.com/benavlabs/FastAPI-boilerplate">
      <img src="https://img.shields.io/badge/DeepWiki-1F2937?style=for-the-badge&logoColor=white" alt="DeepWiki">
  </a>
</p>

## Features

* ⚡️ Fully async FastAPI + SQLAlchemy 2.0
* 🧱 Pydantic v2 models & validation
* 🔐 JWT auth (access + refresh), cookies for refresh
* 👮 Rate limiter + tiers (free/pro/etc.)
* 🧰 FastCRUD for efficient CRUD & pagination
* 🧑‍💼 **CRUDAdmin**: minimal admin panel (optional)
* 🚦 ARQ background jobs (Redis)
* 🧊 Redis caching (server + client-side headers)
* 🌐 Configurable CORS middleware for frontend integration
* 🐳 One-command Docker Compose
* 🚀 NGINX & Gunicorn recipes for prod

## Why and When to use it

**Perfect if you want:**

* A pragmatic starter with auth, CRUD, jobs, caching and rate-limits
* **Sensible defaults** with the freedom to opt-out of modules
* **Docs over boilerplate** in README - depth lives in the site

> **Not a fit** if you need a monorepo microservices scaffold - [see the docs](https://benavlabs.github.io/FastAPI-boilerplate/user-guide/project-structure/) for pointers.

**What you get:**

* **App**: FastAPI app factory, [env-aware docs](https://benavlabs.github.io/FastAPI-boilerplate/user-guide/development/) exposure
* **Auth**: [JWT access/refresh](https://benavlabs.github.io/FastAPI-boilerplate/user-guide/authentication/), logout via token blacklist
* **DB**: Postgres + SQLAlchemy 2.0, [Alembic migrations](https://benavlabs.github.io/FastAPI-boilerplate/user-guide/database/)
* **CRUD**: [FastCRUD generics](https://benavlabs.github.io/FastAPI-boilerplate/user-guide/database/crud/) (get, get_multi, create, update, delete, joins)
* **Caching**: [decorator-based endpoints cache](https://benavlabs.github.io/FastAPI-boilerplate/user-guide/caching/); client cache headers
* **Queues**: [ARQ worker](https://benavlabs.github.io/FastAPI-boilerplate/user-guide/background-tasks/) (async jobs), Redis connection helpers
* **Rate limits**: [per-tier + per-path rules](https://benavlabs.github.io/FastAPI-boilerplate/user-guide/rate-limiting/)
* **Admin**: [CRUDAdmin views](https://benavlabs.github.io/FastAPI-boilerplate/user-guide/admin-panel/) for common models (optional)

This is what we've been using in production apps. Several applications running in production started from this boilerplate as their foundation - from SaaS platforms to internal tools. It's proven, stable technology that works together reliably. Use this as the foundation for whatever you want to build on top.

> **Building an AI SaaS?** Skip even more setup with [**FastroAI**](https://fastro.ai) - our production-ready template with AI integration, payments, and frontend included.

## TL;DR - Quickstart

Use the template on GitHub, create your repo, then:

```bash
git clone https://github.com/<you>/FastAPI-boilerplate
cd FastAPI-boilerplate
```

**Quick setup:** Run the interactive setup script to choose your deployment configuration:

```bash
./setup.py
```

Or directly specify the deployment type: `./setup.py local`, `./setup.py staging`, or `./setup.py production`.

The script copies the right files for your deployment scenario. Here's what each option sets up:

### Option 1: Local development with Uvicorn

Best for: **Development and testing**

**Copies:**

- `scripts/local_with_uvicorn/Dockerfile` → `Dockerfile`
- `scripts/local_with_uvicorn/docker-compose.yml` → `docker-compose.yml`
- `scripts/local_with_uvicorn/.env.example` → `src/.env`

Sets up Uvicorn with auto-reload enabled. The example environment values work fine for development.

**Manual setup:** `./setup.py local` or copy the files above manually.

### Option 2: Staging with Gunicorn managing Uvicorn workers

Best for: **Staging environments and load testing**

**Copies:**

- `scripts/gunicorn_managing_uvicorn_workers/Dockerfile` → `Dockerfile`
- `scripts/gunicorn_managing_uvicorn_workers/docker-compose.yml` → `docker-compose.yml`
- `scripts/gunicorn_managing_uvicorn_workers/.env.example` → `src/.env`

Sets up Gunicorn managing multiple Uvicorn workers for production-like performance testing.

> [!WARNING]
> Change `SECRET_KEY` and passwords in the `.env` file for staging environments.

**Manual setup:** `./setup.py staging` or copy the files above manually.

### Option 3: Production with NGINX

Best for: **Production deployments**

**Copies:**

- `scripts/production_with_nginx/Dockerfile` → `Dockerfile`
- `scripts/production_with_nginx/docker-compose.yml` → `docker-compose.yml`
- `scripts/production_with_nginx/.env.example` → `src/.env`

Sets up NGINX as reverse proxy with Gunicorn + Uvicorn workers for production.

> [!CAUTION]
> You MUST change `SECRET_KEY`, all passwords, and sensitive values in the `.env` file before deploying!

**Manual setup:** `./setup.py production` or copy the files above manually.

---

**Start your application:**

```bash
docker compose up
```

**Access your app:**
- **Local**: http://127.0.0.1:8000 (auto-reload enabled) → [API docs](http://127.0.0.1:8000/docs)
- **Staging**: http://127.0.0.1:8000 (production-like performance)
- **Production**: http://localhost (NGINX reverse proxy)

### Next steps

**Create your first admin user:**
```bash
docker compose run --rm create_superuser
```

**Run database migrations** (if you add models):
```bash
cd src && uv run alembic revision --autogenerate && uv run alembic upgrade head
```

**Test background jobs:**
```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/tasks/task?message=hello'
```

**Or run locally without Docker:**
```bash
uv sync && uv run uvicorn src.app.main:app --reload
```

> Full setup (from-scratch, .env examples, PostgreSQL & Redis, gunicorn, nginx) lives in the [docs](https://benavlabs.github.io/FastAPI-boilerplate/getting-started/installation/).

## Configuration (minimal)

Create `src/.env` and set **app**, **database**, **JWT**, and **environment** settings. See the [docs](https://benavlabs.github.io/FastAPI-boilerplate/getting-started/configuration/) for a copy-pasteable example and production guidance.

[https://benavlabs.github.io/FastAPI-boilerplate/getting-started/configuration/](https://benavlabs.github.io/FastAPI-boilerplate/getting-started/configuration/)

* `ENVIRONMENT=local|staging|production` controls API docs exposure
* Set `ADMIN_*` to enable the first admin user

## Common tasks

```bash
# run locally with reload (without Docker)
uv sync && uv run uvicorn src.app.main:app --reload

# run Alembic migrations
cd src && uv run alembic revision --autogenerate && uv run alembic upgrade head

# enqueue a background job (example endpoint)
curl -X POST 'http://127.0.0.1:8000/api/v1/tasks/task?message=hello'
```

More examples (superuser creation, tiers, rate limits, admin usage) in the [docs](https://benavlabs.github.io/FastAPI-boilerplate/getting-started/first-run/).

## Background jobs & ARQ

This boilerplate ships with [ARQ](https://github.com/samuelcolvin/arq) as the default async background worker built on top of Redis. It is proven and works well for many use cases, but is currently in maintenance mode rather than active feature development.

For most projects, ARQ is still a solid choice if:

- you are comfortable with Redis as the only dependency for background jobs, and
- you prefer a lightweight, fully-async worker that integrates nicely with FastAPI.

If your team expects to invest heavily in background processing (workflows, retries, scheduling, monitoring, etc.), you may want to:

- keep ARQ for now and plan a migration path later, or
- swap ARQ out for another worker (e.g. RQ, Celery, Dramatiq, or a hosted solution) behind the same queue abstractions.

See the [background tasks guide](https://benavlabs.github.io/FastAPI-boilerplate/user-guide/background-tasks/) for more details on how ARQ is wired into this project and how to adapt it to your own needs.

## Contributing

Read [contributing](CONTRIBUTING.md).

## References

This project was inspired by a few projects, it's based on them with things changed to the way I like (and pydantic, sqlalchemy updated)

- [`Full Stack FastAPI and PostgreSQL`](https://github.com/tiangolo/full-stack-fastapi-postgresql) by @tiangolo himself
- [`FastAPI Microservices`](https://github.com/Kludex/fastapi-microservices) by @kludex which heavily inspired this boilerplate
- [`Async Web API with FastAPI + SQLAlchemy 2.0`](https://github.com/rhoboro/async-fastapi-sqlalchemy) for sqlalchemy 2.0 ORM examples
- [`FastaAPI Rocket Boilerplate`](https://github.com/asacristani/fastapi-rocket-boilerplate/tree/main) for docker compose

## License

[`MIT`](LICENSE.md)

## Contact

Benav Labs – [benav.io](https://benav.io), [discord server](https://discord.com/invite/TEmPs22gqB)

<hr>
<a href="https://benav.io">
  <img src="https://github.com/benavlabs/fastcrud/raw/main/docs/assets/benav_labs_banner.png" alt="Powered by Benav Labs - benav.io"/>
</a>
