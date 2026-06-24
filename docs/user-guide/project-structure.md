# Project Structure

The codebase follows a three-layer architecture (**interfaces / infrastructure / modules**) with **vertical-slice modules** — each feature owns its models, schemas, CRUD, service, and routes in one folder. This guide explains how everything is organized and where to put new code.

## Repository Root

```text
fastapi-boilerplate/
├── backend/                  # Python project root (see below)
├── docs/                     # zensical documentation
├── .github/                  # CI workflows
├── README.md
└── LICENSE.md
```

The Python project lives entirely under `backend/`. If you ever add a frontend, it would sit alongside as `frontend/`.

## Backend Layout

```text
backend/
├── pyproject.toml            # Dependencies and tooling config
├── uv.lock                   # Locked dependency versions
├── Dockerfile                # Container image for the app
├── alembic.ini               # Alembic migration config
├── .env.example              # Reference for environment variables
├── migrations/               # Alembic migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── scripts/                  # One-off setup scripts
│   ├── create_first_superuser.py
│   ├── create_first_tier.py
│   ├── create_tables.py
│   └── setup_initial_data.py
├── src/                      # Application source (the three layers below)
└── tests/                    # Test suite (unit + integration)
```

### Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Project metadata, dependencies (`[project]`), tooling config (ruff, mypy, pytest) |
| `uv.lock` | Locks exact dependency versions for reproducible installs |
| `Dockerfile` | Multi-stage build: requirements export → base → dev/prod/migrate stages |
| `alembic.ini` | Alembic settings (script location, logging) |
| `.env.example` | Documented reference of every environment variable |

## The Three Layers (`src/`)

```text
src/
├── interfaces/               # HOW the world talks to the app (HTTP, admin UI)
├── infrastructure/           # WHAT the app uses (DB, cache, auth, taskiq, config)
└── modules/                  # WHAT the app IS (vertical-slice feature modules)
```

The flow is **interfaces → modules → infrastructure**:

- `interfaces` mounts routers, middleware, and the admin UI.
- `modules` express domain features. Each one is self-contained.
- `infrastructure` provides the cross-cutting plumbing every layer above can reach for.

Modules don't import each other directly except for the shared `common` module. Interfaces don't contain business logic. Infrastructure doesn't know about specific features.

### `src/interfaces/`

```text
interfaces/
├── main.py                   # FastAPI app instance + lifespan + middleware setup
├── api/
│   ├── __init__.py           # Mounts /api router
│   └── v1/
│       └── __init__.py       # Mounts /v1 + each module's router
└── admin/
    ├── initialize.py         # SQLAdmin setup (mounted at /admin)
    ├── auth.py               # Admin auth backend
    ├── mixins.py
    └── views/                # SQLAdmin model views (Tier, User, etc.)
```

`main.py` is the entry point — `uv run fastapi dev src/interfaces/main.py` starts here. The `v1/__init__.py` aggregator imports each module's `routes` and includes them under the right prefix.

### `src/infrastructure/`

```text
infrastructure/
├── app_factory.py            # Builds the FastAPI app (CORS, GZip, middleware, lifespan)
├── middleware.py             # ClientCache, SecurityHeaders, etc.
├── config/                   # Settings + Pydantic-driven env loading
│   ├── settings.py
│   └── enums.py
├── database/                 # SQLAlchemy engine, session, base model
├── auth/                     # crudauth wiring: deps, OAuth, route handlers
│   ├── setup.py              # The `auth = CRUDAuth(...)` singleton (composition root)
│   ├── dependencies.py       # get_current_user / _superuser / _optional_user + Principal deps
│   ├── oauth.py              # crudauth OAuth building blocks (Google wired)
│   ├── routes.py             # /auth/login, /logout, /oauth/google, /check-auth
│   └── http_exceptions.py    # fastcrud HTTP exception re-export
├── cache/                    # Redis/Memcached cache + decorator
│   └── backends/
├── rate_limit/               # Rate limiter middleware + Redis/Memcached backends
│   └── backends/
├── taskiq/                   # Async task queue (broker, worker entry point, registry)
├── security/                 # Production security validator
└── logging/                  # Centralized logging configuration
```

`infrastructure/auth/routes.py` is intentionally placed here (instead of in a `modules/auth/` folder) because authentication is structural — every feature relies on it.

### `src/modules/` — Vertical-Slice Features

```text
modules/
├── common/                   # Cross-module shared schemas, exceptions, utils
│   ├── constants.py
│   ├── exceptions.py
│   ├── schemas.py
│   └── utils/
├── user/
│   ├── models.py             # SQLAlchemy User model
│   ├── schemas.py            # Pydantic UserCreate, UserRead, UserUpdate, etc.
│   ├── crud.py               # FastCRUD wrapper (crud_users)
│   ├── service.py            # Business logic (UserService)
│   ├── routes.py             # APIRouter with /users endpoints
│   └── enums.py              # OAuthProvider, etc.
├── tier/                     # Subscription tiers (model + simple CRUD)
├── rate_limit/               # Per-tier rate limit definitions
└── api_keys/                 # API keys, key usage, key permissions
```

Each module is **self-contained**: drop it in, drop it out, with minimal blast radius. The aggregator at `interfaces/api/v1/__init__.py` is the only place that knows about every module's router.

### Common Module Files

| File | Purpose |
|------|---------|
| `models.py` | SQLAlchemy ORM models (table schema) |
| `schemas.py` | Pydantic request/response models |
| `crud.py` | FastCRUD instances for the model |
| `service.py` | Business logic — orchestrates CRUD calls, applies rules |
| `routes.py` | `APIRouter` with the module's endpoints |
| `enums.py` | StrEnum types if the module needs them (optional) |

## Migrations (`backend/migrations/`)

```text
migrations/
├── env.py                    # Alembic environment (loads all models)
├── script.py.mako            # Template for new migrations
└── versions/                 # One file per migration revision
```

Run from `backend/`:

```bash
uv run alembic revision --autogenerate -m "add foo"
uv run alembic upgrade head
```

## Scripts (`backend/scripts/`)

```text
scripts/
├── setup_initial_data.py     # All-in-one: tables + tier + admin
├── create_first_superuser.py # Just the admin user
├── create_first_tier.py      # Just the default tier
└── create_tables.py          # Just the database tables
```

The most common entry point is `setup_initial_data` which calls all three.

```bash
uv run python -m scripts.setup_initial_data
```

## Tests (`backend/tests/`)

```text
tests/
├── conftest.py               # Pytest fixtures (Postgres testcontainer, db session, client, mocks)
├── unit/                     # Unit tests (no external deps)
│   ├── infrastructure/
│   └── modules/
└── integration/              # Integration tests (real Postgres via testcontainers)
```

Run from `backend/`:

```bash
uv run pytest tests/unit       # fast, no Docker
uv run pytest tests/integration  # spins up Postgres in Docker via testcontainers
uv run pytest                  # everything
```

## Architectural Patterns

### Three-Layer Architecture

1. **Interfaces** (`interfaces/`) - HTTP routes, admin UI, the FastAPI app instance
2. **Modules** (`modules/`) - Domain features as vertical slices
3. **Infrastructure** (`infrastructure/`) - Cross-cutting plumbing (DB, cache, auth, queue, config, logging)

Dependencies flow downward: interfaces depend on modules and infrastructure; modules depend on infrastructure (and `modules/common`). Infrastructure has no upward dependencies.

### Vertical Slices

Each `modules/<feature>/` folder owns the entire stack for that feature. Adding a new feature means adding **one** new folder, not editing five separate top-level directories.

### Dependency Injection

FastAPI's `Depends` is used throughout:

- **Database session** — `Depends(async_session)` from `infrastructure.database.session`
- **Current user** — `Depends(get_current_user)` from `infrastructure.auth.dependencies`
- **Superuser only** — `Depends(get_current_superuser)`
- **Service instances** — Each module's `routes.py` defines its own `get_<feature>_service()` factory

### Configuration

All configuration lives in `infrastructure/config/settings.py`, loaded from `.env`:

- Settings classes grouped by concern (`DatabaseSettings`, `CacheSettings`, `AuthSettings`, etc.)
- A single `Settings` class composes them
- `get_settings()` returns a cached singleton

### Error Handling

- Domain exceptions in `modules/common/exceptions.py` (e.g. `ResourceNotFoundError`, `PermissionDeniedError`)
- HTTP-shaped exceptions in `infrastructure/auth/http_exceptions.py`
- Routes catch domain exceptions and translate them via `modules/common/utils/error_handler.handle_exception`

## Adding a New Feature

The recommended flow:

1. **Create the module folder**: `mkdir backend/src/modules/widgets`
2. **Define the model**: `backend/src/modules/widgets/models.py`
3. **Add schemas**: `backend/src/modules/widgets/schemas.py`
4. **Wrap with FastCRUD**: `backend/src/modules/widgets/crud.py`
5. **Write the service**: `backend/src/modules/widgets/service.py`
6. **Expose routes**: `backend/src/modules/widgets/routes.py`
7. **Register the router** in `backend/src/interfaces/api/v1/__init__.py`
8. **Generate a migration**: `uv run alembic revision --autogenerate -m "add widgets"`
9. **Apply**: `uv run alembic upgrade head`

See [Development Guide](development.md) for a full walkthrough.

## Data Flow

```text
HTTP Request
    → interfaces/api/v1/__init__.py
    → modules/<feature>/routes.py
    → modules/<feature>/service.py
    → modules/<feature>/crud.py (FastCRUD)
    → infrastructure/database/session.py
    → PostgreSQL

HTTP Response ← Pydantic schema ← service ← CRUD result ← DB query
```

This layering keeps HTTP concerns out of business logic, and business logic out of data access — making the codebase straightforward to navigate, test, and extend.
