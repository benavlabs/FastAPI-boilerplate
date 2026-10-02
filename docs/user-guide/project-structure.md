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
│   ├── seeders.py            # The seeders the selected features contribute
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
├── modules/                  # WHAT the app IS (vertical-slice feature modules)
└── wiring/                   # WHICH features this project selected
```

The flow is **interfaces → modules → infrastructure**:

- `interfaces` mounts routers, middleware, and the admin UI.
- `modules` express domain features. Each one is self-contained.
- `infrastructure` provides the cross-cutting plumbing every layer above can reach for.
- `wiring` is the composition root: the one place that names every feature.

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
    ├── initialize.py         # SQLAdmin setup (mounted at /admin by its installer)
    ├── auth.py               # Admin auth backend, with its own session middleware
    ├── settings.py           # The admin feature's settings mixin
    └── mixins.py
```

`main.py` is the entry point — `uv run --no-sync fastapi dev src/interfaces/main.py` starts here; it also serves `/health` and `/health/ready`. The `v1/__init__.py` aggregator mounts the routers `wiring/app.py` lists, so it never names a feature. Each feature's admin views live with the feature, in `modules/<feature>/admin.py`.

### `src/infrastructure/`

```text
infrastructure/
├── app_factory.py            # Builds the FastAPI app (CORS, GZip, middleware, lifespan)
├── middleware.py             # ClientCache, SecurityHeaders, etc.
├── config/                   # Settings + Pydantic-driven env loading
│   ├── settings.py
│   └── enums.py
├── composition.py            # The shapes features contribute (RouterMount, Lifecycle, …)
├── permissions.py            # The permission registry every module declares into
├── dependencies.py           # AsyncSessionDep — the deps every project has
├── database/                 # SQLAlchemy engine, session, base model, readiness
├── auth/                     # The accounts feature: crudauth setup, deps, route handlers
│   ├── setup.py              # The `auth = CRUDAuth(...)` singleton
│   ├── dependencies.py       # get_current_user / _superuser / _optional_user
│   ├── deps.py               # The annotated caller dependencies (CurrentUserDep, …)
│   ├── authorization.py      # require_permissions and the permission resolution
│   ├── routes.py             # /auth/login, /logout, /oauth, /check-auth
├── cache/                    # Redis/Memcached cache + decorator + readiness
│   └── backends/
├── ratelimit/                # The API throttle dependency
├── redis.py                  # Shared Redis clients injected into crudauth and the cache
├── taskiq/                   # Async task queue (broker, worker entry point, registry)
├── security/                 # Production security validator
└── logging/                  # Centralized logging configuration
```

`infrastructure/auth/routes.py` is intentionally placed here (instead of in a `modules/auth/` folder) because authentication is structural — every feature relies on it. It's still a feature that can be removed: everything accounts owns lives under `auth/` and `modules/user/`.

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
│   ├── permissions.py        # UserPermission StrEnum (user.read, user.update, ...)
│   └── enums.py              # OAuthProvider, etc.
├── role/                     # RBAC: Role, RolePermission, UserRole
├── tier/                     # Subscription tiers (model + simple CRUD)
├── rate_limit/               # Per-tier rate limit definitions
└── api_keys/                 # API keys, key usage, key permissions
```

Each module is **self-contained**: drop it in, drop it out, with minimal blast radius. `src/wiring/` is the only place that knows which modules this project selected, and `tools/removal_drill.py` checks that dropping one out really works — see [Composable Features](composable-features.md).

### Common Module Files

| File | Purpose |
|------|---------|
| `models.py` | SQLAlchemy ORM models (table schema) |
| `schemas.py` | Pydantic request/response models |
| `crud.py` | FastCRUD instances for the model |
| `service.py` | Business logic — orchestrates CRUD calls, applies rules |
| `routes.py` | `APIRouter` with the module's endpoints |
| `permissions.py` | `StrEnum` of the module's permissions, registered with `@register_permissions` (optional) |
| `enums.py` | StrEnum types if the module needs them (optional) |
| `settings.py` | The module's settings mixin, composed in `wiring/settings.py` (optional) |
| `contrib.py` | Columns and schema fields the module adds to another model (optional) |
| `hooks.py` | What the module contributes to another feature's extension points (optional) |
| `admin.py` | The module's SQLAdmin views, listed in `wiring/admin.py` (optional) |

### `src/wiring/` — The Composition Root

```text
wiring/
├── app.py                    # ROUTER_MOUNTS, ROOT_ROUTERS, API_THROTTLE, LIFECYCLES, INSTALLERS, DOCS_GUARD
├── settings.py               # Each feature's settings mixin, core last
├── hooks.py                  # PERMISSION_SOURCES, RATE_LIMIT_RESOLVERS, TIER_DELETE_GUARDS, READINESS_CHECKS
├── models.py                 # What features add to the User model and its schemas
└── admin.py                  # ADMIN_VIEWS
```

These files are imports and names only — no decisions — so ruff, mypy and your IDE see exactly what the project wired. Removing a feature means deleting its folders and its lines here. [Composable Features](composable-features.md) covers the contribution shapes and the removal drill.

## Migrations (`backend/migrations/`)

```text
migrations/
├── env.py                    # Alembic environment (loads all models)
├── script.py.mako            # Template for new migrations
└── versions/                 # One file per migration revision
```

Run from `backend/`:

```bash
uv run --no-sync alembic revision --autogenerate -m "add foo"
uv run --no-sync alembic upgrade head
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
uv run --no-sync python -m scripts.setup_initial_data
```

Each script also runs on its own, from `backend/`:

```bash
uv run --no-sync python scripts/create_first_tier.py
uv run --no-sync python scripts/create_first_superuser.py
```

A script that can't do its job - admin settings that don't describe an account, a password the
policy refuses, a username someone already has, a database it can't reach - logs one line and exits
`1`.

## Tests (`backend/tests/`)

```text
tests/
├── conftest.py               # Postgres testcontainer, db session, client, mocks
├── wiring.py                 # The fixture modules pytest loads for the selected features
├── fixtures/                 # Each feature's own fixtures
├── unit/                     # Unit tests (no external deps)
│   ├── infrastructure/
│   └── modules/
└── integration/              # Integration tests (real Postgres via testcontainers)
```

Run from `backend/`:

```bash
uv run --no-sync pytest tests/unit         # fast, no Docker
uv run --no-sync pytest tests/integration  # spins up Postgres in Docker via testcontainers
uv run --no-sync pytest                    # everything
```

## Architectural Patterns

### Three-Layer Architecture

1. **Interfaces** (`interfaces/`) - HTTP routes, admin UI, the FastAPI app instance
2. **Modules** (`modules/`) - Domain features as vertical slices
3. **Infrastructure** (`infrastructure/`) - Cross-cutting plumbing (DB, cache, auth, queue, config, logging)

Dependencies flow downward: interfaces depend on modules and infrastructure; modules depend on infrastructure (and `modules/common`). Infrastructure has no upward dependencies.

`wiring/` sits above all three: it imports from every layer, and the layers import *only its lists* — `api/v1/__init__.py` reads `ROUTER_MOUNTS`, `auth/authorization.py` reads `PERMISSION_SOURCES`, `modules/user/models.py` reads `UserModelExtensions`, and so on. That's how a feature reaches another one without importing it.

### Vertical Slices

Each `modules/<feature>/` folder owns the entire stack for that feature. Adding a new feature means adding **one** new folder, not editing five separate top-level directories.

### Dependency Injection

FastAPI's `Depends` is used throughout:

- **Database session** — `Depends(async_session)` from `infrastructure.database.session`
- **Current user** — `Depends(get_current_user)` from `infrastructure.auth.dependencies`
- **Superuser only** — `Depends(get_current_superuser)`
- **Permission required** — `require_permissions("user.read")` in the route's `dependencies` list
- **Service instances** — Each module's `routes.py` defines its own `get_<feature>_service()` factory

`infrastructure/dependencies.py` holds the one alias every project has, `AsyncSessionDep`. The aliases that resolve a caller ship with accounts, in `infrastructure/auth/deps.py` — `CurrentUserDep`, `CurrentSuperUserDep`, `OptionalUserDep`, `CurrentPrincipalDep` (the crudauth `Principal`) and `CurrentPermissionsDep` (the caller's effective permissions, resolved once per request).

### Configuration

Configuration is loaded from `.env` and assembled from mixins:

- The core mixins (`DatabaseSettings`, `CORSSettings`, `SecuritySettings`, …) live in `infrastructure/config/base.py`
- Each feature ships its own mixin next to its code (`infrastructure/cache/settings.py`, `modules/tier/settings.py`, …)
- `wiring/settings.py` composes the selected ones into `Settings`, with the core last so a feature can override a core default
- `infrastructure/config/settings.py` is the stable facade: import `settings` or `get_settings()` from there whatever features are installed

### Error Handling

- Domain exceptions in `modules/common/exceptions.py` — `DomainError` and the few shapes every feature shares (`ResourceNotFoundError`, `ResourceExistsError`, `ValidationError`, `PermissionDeniedError`, `PersistenceError`)
- A feature subclasses those for its own errors and sets `public_detail` to choose what the client is told, so the mapping never names a feature's exceptions
- HTTP-shaped exceptions in `infrastructure/http_exceptions.py`
- `modules/common/utils/error_handler.register_exception_handlers(app)` installs one handler that maps any `DomainError` through `map_exception`, so routes raise and don't translate

## Adding a New Feature

The recommended flow:

1. **Create the module folder**: `mkdir backend/src/modules/widgets`
2. **Define the model**: `backend/src/modules/widgets/models.py`
3. **Add schemas**: `backend/src/modules/widgets/schemas.py`
4. **Wrap with FastCRUD**: `backend/src/modules/widgets/crud.py`
5. **Write the service**: `backend/src/modules/widgets/service.py`
6. **Expose routes**: `backend/src/modules/widgets/routes.py`
7. **Register the router**: add a `RouterMount` to `ROUTER_MOUNTS` in `backend/src/wiring/app.py`
8. **Wire the rest of it**: its settings mixin in `wiring/settings.py`, its hook contributions in `wiring/hooks.py`, its admin views in `wiring/admin.py`, its fixtures in `tests/wiring.py` — whichever it has
9. **Add it to the removal drill**: list its paths in `tools/removal_drill.py` so a build without it is checked
10. **Generate a migration**: `uv run --no-sync alembic revision --autogenerate -m "add widgets"`
11. **Apply**: `uv run --no-sync alembic upgrade head`

See [Development Guide](development.md) for a full walkthrough.

## Data Flow

```text
HTTP Request
    → interfaces/api/v1/__init__.py (mounting what wiring/app.py lists)
    → modules/<feature>/routes.py
    → modules/<feature>/service.py
    → modules/<feature>/crud.py (FastCRUD)
    → infrastructure/database/session.py
    → PostgreSQL

HTTP Response ← Pydantic schema ← service ← CRUD result ← DB query
```

This layering keeps HTTP concerns out of business logic, and business logic out of data access — making the codebase straightforward to navigate, test, and extend.
