# Development Guide

This page covers the day-to-day development loop: running the app, the tools that ship with it, how to add a new module, and what to know about debugging the boilerplate's moving parts.

For end-to-end "how do I add an entity," see:

- **[Database → Models](database/models.md)** — defining `Base`-derived dataclass models
- **[Database → Schemas](database/schemas.md)** — request/response Pydantic models
- **[API → Endpoints](api/endpoints.md)** — wiring routes to services
- **[Admin Panel → Adding Models](admin-panel/adding-models.md)** — surfacing the model in the admin UI

This page is the meta-guide that ties them together.

## Running the App

```bash
cd backend
uv run fastapi dev src/interfaces/main.py
```

`--reload` watches the filesystem and restarts on Python file changes. Use it for development; **never** in production.

If you're using Docker:

```bash
docker compose up -d                # API + Postgres + Redis
docker compose logs -f api          # tail the api logs
docker compose exec api bash        # shell into the api container
```

The service names depend on your `docker-compose.yml`; the `api` name is conventional.

## The Background Worker

If your app uses Taskiq tasks, run a worker alongside the API in a second terminal:

```bash
cd backend
uv run taskiq worker infrastructure.taskiq.worker:default_broker --reload
```

`--reload` is dev-only; drop it in production. See [Background Tasks](background-tasks/index.md) for details.

## The Dev Toolchain

The project ships configured `ruff`, `mypy`, and `pytest` via `backend/pyproject.toml`:

```bash
cd backend

# Lint + format (ruff handles both)
uv run ruff check .
uv run ruff format .
uv run ruff check --fix .          # auto-fix what ruff can

# Type check
uv run mypy src

# Tests
uv run pytest
uv run pytest -k "test_user"       # run tests matching a name
uv run pytest -x                   # stop on first failure
uv run pytest -n auto              # parallel via pytest-xdist
```

Ruff is configured (`pyproject.toml:[tool.ruff]`) with:

- `line-length = 128`
- Selected rule sets: `E`, `F`, `I`, `UP` (pyflakes, pycodestyle, isort, pyupgrade)
- `known-first-party = ["src"]` so `src.*` imports are grouped correctly

Mypy is intentionally relaxed (`disallow_untyped_defs = false`) — adopt strictness gradually as you add types to new modules.

## Pre-Commit

The repo's `.pre-commit-config.yaml` wires up ruff, pyupgrade, docformatter, mdformat, and a few standard hygiene hooks (trailing whitespace, large files, private keys). Install once:

```bash
pip install pre-commit
pre-commit install
```

After that, `git commit` runs the hooks automatically. To run them ad hoc:

```bash
pre-commit run --all-files
```

## Adding a New Module

The boilerplate organizes domain code under `backend/src/modules/<name>/` with a vertical-slice layout. To add a `widgets` module:

```text
backend/src/modules/widgets/
├── __init__.py
├── models.py        # SQLAlchemy model (Base + dataclass)
├── schemas.py       # Pydantic request/response models
├── crud.py          # FastCRUD instance
├── service.py       # Business logic — calls CRUD, raises domain errors
└── routes.py        # FastAPI router — wraps the service, handles HTTP
```

The full pattern (with concrete code) is in [Database → Models](database/models.md) and [API → Endpoints](api/endpoints.md). The short version:

1. **Write the model** in `models.py`. Inherit from `Base`, use mixins (`TimestampMixin`, `SoftDeleteMixin`, `UUIDMixin`) where they apply.
2. **Write the schemas** in `schemas.py`. Standard set: `WidgetBase`, `WidgetCreate`, `WidgetRead`, `WidgetUpdate`, plus `WidgetSelect` for FastCRUD's `schema_to_select`.
3. **Wire FastCRUD** in `crud.py`:
   ```python
   from fastcrud import FastCRUD
   from .models import Widget
   crud_widgets = FastCRUD(Widget)
   ```
4. **Implement the service** in `service.py` with class methods that call `crud_widgets`, raise `DomainError` subclasses on bad state.
5. **Define routes** in `routes.py`. Wrap the service, catch domain exceptions via `handle_exception`, return dicts (FastAPI serializes through `response_model=WidgetRead`).
6. **Register the router** in `interfaces/main.py` (or wherever your top-level routers are aggregated):
   ```python
   from src.modules.widgets.routes import router as widgets_router
   api_v1.include_router(widgets_router, prefix="/widgets")
   ```
7. **Generate a migration**:
   ```bash
   cd backend
   uv run alembic revision --autogenerate -m "Add widget model"
   uv run alembic upgrade head
   ```
   Note: `validate_production_migration` runs at the start of `env.py` and refuses to apply migrations in production unless `CONFIRM_PRODUCTION_MIGRATION=yes` is set. Local development is unaffected.
8. **(Optional)** Add a `WidgetAdmin` view — see [Admin Panel → Adding Models](admin-panel/adding-models.md).

The Alembic env (`backend/migrations/env.py`) auto-discovers models via `import_models("src.modules")`, so new modules are picked up by `--autogenerate` without any manual import wiring — provided your model is in `modules/<name>/models.py`.

## Adding Custom Middleware

Middleware lives at `backend/src/infrastructure/middleware.py` (or a peer file you create). The pattern:

```python
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
        return response
```

Register in `infrastructure/app_factory.py` (or your overridden `create_application`):

```python
application.add_middleware(TimingMiddleware)
```

Order matters — middleware added later runs **earlier** in the request path. The boilerplate's own middlewares (`SecurityHeadersMiddleware`, `ClientCacheMiddleware`, `RateLimiterMiddleware`, `SessionMiddleware`, etc.) are added in a deliberate order; see `app_factory.py:create_application`.

## Adding a Custom Dependency

Dependencies belong with the feature they serve. For session-aware dependencies, look at `infrastructure/auth/session/dependencies.py:get_current_user` for a template.

### Define the factory

```python
# modules/workspace/dependencies.py
from fastapi import Request

from ...infrastructure.auth.session.dependencies import get_current_user
from ...infrastructure.dependencies import CurrentUserDep


def get_workspace(
    request: Request,
    current_user: CurrentUserDep,
) -> str:
    workspace = request.headers.get("X-Workspace")
    if not workspace:
        raise PermissionDeniedError("Missing workspace header")
    # validate workspace membership against current_user...
    return workspace
```

### Register the alias (optional)

Add it to the module's `dependencies.py` so routes can use it without typing `Depends(get_workspace)` every time:

```python
# modules/workspace/dependencies.py (extended)
from typing import Annotated

from fastapi import Depends

from ...infrastructure.dependencies import CurrentUserDep

WorkspaceDep = Annotated[str, Depends(get_workspace)]
```

### Use it

```python
from ..dependencies import WorkspaceDep


@router.get("/workspace/items")
async def list_workspace_items(
    workspace: WorkspaceDep,
    db: AsyncSessionDep,
) -> list[dict[str, Any]]:
    ...
```

Per-module service aliases follow the same pattern — see the existing `modules/{user,tier,rate_limit,api_keys}/dependencies.py` files for real examples.

## Debugging Tips

### See every SQL query

Set `DATABASE_ECHO=true` in your `.env`. Every statement (and parameter binding) is logged. Useful when investigating why a FastCRUD call returns the wrong shape, or when chasing N+1 issues.

### Inspect rate-limit and cache state

```bash
docker compose exec redis redis-cli
> SELECT 0                           # cache DB
> KEYS '*'
> SELECT 1                           # rate-limiter DB
> KEYS 'ratelimit:*'
> SELECT 3                           # taskiq queue DB
> LRANGE default 0 -1                # pending tasks
```

Each subsystem uses a different Redis DB number; see `.env.example` for the conventions (`CACHE_REDIS_DB=0`, `SESSION_REDIS_DB=1`, `RATE_LIMITER_REDIS_DB=1` (yes, the rate limiter shares with sessions in defaults — change one if you want isolation), `TASKIQ_REDIS_DB=3`).

### Watch sessions live

If a user reports being logged out unexpectedly, check the session backend directly:

```python
from src.infrastructure.auth.session import SessionManager
manager = SessionManager()
sessions = await manager.get_user_sessions(user_id=42)
```

See [Authentication → Sessions](authentication/sessions.md) for full details.

### Use the interactive docs

`http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc` are auto-generated from your routes. Send requests directly from the UI; every endpoint that takes a Pydantic body has a "Try it out" form. Only present in non-production by default — gated by `OPENAPI_URL`.

### Production validators

When `ENVIRONMENT=production`, `infrastructure/security/` runs validators at startup that fail loudly on:

- Placeholder `SECRET_KEY`
- `DEBUG=true`
- Unset `CORS_ORIGINS` or `CORS_ORIGINS=*`

If your prod boot is failing with one of those, that's your hint — don't bypass the validator.

## Testing

The repo is **set up** for `pytest` but doesn't ship example tests yet — `backend/pyproject.toml` configures pytest with:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
env = ["ENVIRONMENT=pytest", "PYTEST_CURRENT_TEST=true"]
```

Tests run with `ENVIRONMENT=pytest`, which the production validator treats as "not production" — your test suite won't be blocked by missing prod-only env vars.

A sane starting `tests/conftest.py`:

```python
# tests/conftest.py
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.database.models import Base
from src.infrastructure.database.session import async_session
from src.interfaces.main import app

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/test_db"


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session):
    async def override_db():
        yield db_session

    app.dependency_overrides[async_session] = override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

Then a smoke test:

```python
# tests/test_smoke.py
async def test_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
```

For tests that genuinely need Postgres semantics (FK constraints, ARRAY types, JSONB), `testcontainers-postgres` is already a dev dependency — spin up a real Postgres in a fixture instead of mocking the database.

For unit tests on services, mock at the **CRUD layer**, not at the database. The service contract is "I call `crud_widgets.get` and get back a dict-or-None"; that's the seam to mock.

## Customizing the Settings

Settings live in `backend/src/infrastructure/config/settings.py`. To add a new env-driven value:

1. Add the field to the relevant settings class (or create a new one):
   ```python
   class WidgetSettings(BaseSettings):
       WIDGET_BATCH_SIZE: int = config("WIDGET_BATCH_SIZE", default=100, cast=int)
   ```
2. Add it to the composed `Settings` mixin list at the bottom of `settings.py`.
3. Document the env var in `backend/.env.example`.

Then read it via `get_settings().WIDGET_BATCH_SIZE`.

See [Configuration → Settings Classes](configuration/settings-classes.md) for the full pattern.

## Disabling Subsystems

Most major subsystems toggle via env vars rather than code changes:

| Subsystem        | Toggle                                | Effect                                      |
|------------------|---------------------------------------|---------------------------------------------|
| Cache            | `CACHE_ENABLED=false`                 | `@cache` becomes a no-op                    |
| Client cache     | `CLIENT_CACHE_ENABLED=false`          | Middleware doesn't mount                    |
| Rate limiter     | `RATE_LIMITER_ENABLED=false`          | `check_rate_limit` returns immediately      |
| Background tasks | Don't run the worker                  | The broker is created but no consumer       |
| Admin panel      | `ADMIN_ENABLED=false`                 | `/admin` is unmounted                       |
| Documentation    | `OPENAPI_URL=`                        | Disables `/docs` and `/redoc`               |

Removing a subsystem entirely (deleting the code) is rare and usually wrong — leaving it disabled costs nothing.

## Common Mistakes

### "Auto-import" gotchas

The boilerplate uses `import_models("src.modules")` in Alembic to discover models. **The discovery walks `modules/<name>/models.py` only.** If you put models in `modules/<name>/sub/inner.py`, autogenerate won't find them. Either keep models in `models.py` or hand-import the file.

### Forgetting `lazy="selectin"` on a relationship

SQLAdmin runs in async context. A relationship without `lazy="selectin"` raises `MissingGreenlet` when the admin tries to render it. Both `User.tier` and other relationships in the boilerplate already use this pattern — copy from those.

### Dataclass models without `init=False` on relationships

`Base = DeclarativeBase + MappedAsDataclass`. Relationship fields must use `init=False` or they end up in the dataclass `__init__` and crash on insert. See `modules/user/models.py:User.tier` for the pattern.

### Catching exceptions too broadly in routes

The route layer catches domain errors (`ResourceNotFoundError`, `PermissionDeniedError`, etc.) and re-raises specific HTTP exceptions. Don't catch them inside the service — services raise; routes translate. The `handle_exception` helper in `modules/common/utils/error_handler.py` does the translation; routes call it as a fallback for unexpected errors.

### Cache decorators without `request: Request`

The `@cache` decorator inspects `request.method` to decide read vs invalidate. The first parameter of every decorated route must be `request: Request`. See [Caching → Server-Side Cache](caching/redis-cache.md) for the rest of the contract.

## Key Files

| Component                    | Location                                                    |
|------------------------------|-------------------------------------------------------------|
| App factory / middleware order | `backend/src/infrastructure/app_factory.py`              |
| Settings                     | `backend/src/infrastructure/config/settings.py`             |
| Lifespan / startup           | `backend/src/infrastructure/app_factory.py:lifespan_factory`|
| Database session             | `backend/src/infrastructure/database/session.py`            |
| Module template (reference)  | `backend/src/modules/user/`                                 |
| Pre-commit                   | `.pre-commit-config.yaml`                                   |
| pyproject (lint / type / test) | `backend/pyproject.toml`                                  |

## Next Steps

- **[Project Structure](project-structure.md)** — full layout walkthrough
- **[Testing](testing.md)** — test patterns and infrastructure
- **[Production](production.md)** — deployment and hardening checklist
