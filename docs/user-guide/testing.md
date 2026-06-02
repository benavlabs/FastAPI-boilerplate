# Testing

The boilerplate ships pytest configured against `backend/tests/`, with `testcontainers-postgres` available for real-database tests and `httpx` for HTTP-level tests against the FastAPI app. **No example tests ship yet** — this page covers the patterns you'll use when you add them.

## What's Configured

`backend/pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
python_classes = ["Test*"]
asyncio_mode = "auto"
env = ["ENVIRONMENT=pytest", "PYTEST_CURRENT_TEST=true"]
markers = [
    "unit: Unit tests that don't require external dependencies",
    "integration: Integration tests that may require external services",
    "asyncio: Tests that use asyncio",
    "slow: marks tests as slow running",
]
```

What this gets you:

- **`pythonpath = ["src"]`** — `from src.modules.user.service import UserService` works without manual sys.path hacks
- **`asyncio_mode = "auto"`** — every `async def test_*` runs under pytest-asyncio; no decorator needed
- **`ENVIRONMENT=pytest`** — the production validator skips its checks (sees a non-`production` env), so you don't need a real `SECRET_KEY` to boot the test app
- **Markers** for `unit` / `integration` / `slow` — use them to split your suite

Available test dependencies (from `[dependency-groups].dev`):

- `pytest`, `pytest-asyncio`, `pytest-mock`
- `httpx` — for in-process HTTP testing
- `faker` — for realistic fixture data
- `testcontainers` + `testcontainers-postgres` — for real-Postgres integration tests
- `pytest-xdist[psutil]` — for parallel test execution

The repo doesn't currently bundle `pytest-cov`. Add it (`uv add --dev pytest-cov`) when you start tracking coverage.

## Test Layout

Use `tests/` at the repository root. A standard layout:

```text
tests/
├── conftest.py                  # global fixtures (app, db, client)
├── helpers/
│   ├── __init__.py
│   └── factories.py             # data-creation helpers (faker-based)
├── unit/
│   ├── modules/
│   │   ├── user/
│   │   │   ├── test_service.py
│   │   │   └── test_schemas.py
│   │   └── tier/
│   │       └── test_service.py
│   └── infrastructure/
│       └── test_session_manager.py
└── integration/
    ├── api/
    │   ├── test_auth.py
    │   ├── test_users.py
    │   └── test_tiers.py
    └── db/
        └── test_migrations.py
```

The split is a guideline, not a rule:

- **Unit tests** mock the database (often by mocking the FastCRUD layer) and run fast
- **Integration tests** use a real Postgres (via testcontainers or a local DB) and exercise the HTTP layer

## A Working `conftest.py`

This is the conftest you'd start from. It provides three layers of fixtures: the FastAPI `app`, an async `db_session`, and an `httpx.AsyncClient` whose database dependency is overridden to use the test session.

```python
# tests/conftest.py
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from src.infrastructure.database.models import Base
from src.infrastructure.database.session import async_session
from src.interfaces.main import app


@pytest_asyncio.fixture(scope="session")
async def postgres_container() -> AsyncGenerator[PostgresContainer, None]:
    container = PostgresContainer("postgres:16-alpine", driver="asyncpg")
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest_asyncio.fixture(scope="session")
async def db_engine(postgres_container):
    url = postgres_container.get_connection_url()
    engine = create_async_engine(url, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    async def override_db():
        yield db_session

    app.dependency_overrides[async_session] = override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

Key things to notice:

- **`testcontainers.PostgresContainer`** spins up a real Postgres, scoped to the test session. First test pays a few seconds of startup; later tests are fast.
- **`db_session`** rolls back at the end of every test, so tests don't bleed into each other. The container is reused; the data is not.
- **`app.dependency_overrides[async_session]`** swaps the production dependency for one that yields the test session — every route ends up reading/writing through your test transaction.
- **`ASGITransport`** runs the FastAPI app in-process — no real HTTP server is started.

If you don't want to depend on Docker for tests, swap `PostgresContainer` for a connection to a local Postgres (e.g. one already running for development). Use a separate database name (`test_db`, dropped at the end of the session).

## Writing Unit Tests

Unit tests should not touch the database. Mock at the **CRUD layer** — your service contract is "I call `crud_widgets.get` and get back a dict-or-None", and that's the seam.

```python
# tests/unit/modules/user/test_service.py
from unittest.mock import AsyncMock

import pytest

from src.modules.common.exceptions import ResourceNotFoundError
from src.modules.user.service import UserService


@pytest.mark.unit
async def test_get_by_id_returns_user(mocker):
    mock_crud = mocker.patch("src.modules.user.service.crud_users")
    mock_crud.get = AsyncMock(return_value={"id": 1, "username": "alice"})

    user = await UserService().get_by_id(user_id=1, db=AsyncMock())

    assert user["username"] == "alice"
    mock_crud.get.assert_awaited_once()


@pytest.mark.unit
async def test_get_by_id_raises_when_missing(mocker):
    mock_crud = mocker.patch("src.modules.user.service.crud_users")
    mock_crud.get = AsyncMock(return_value=None)

    with pytest.raises(ResourceNotFoundError):
        await UserService().get_by_id(user_id=999, db=AsyncMock())
```

`pytest-mock`'s `mocker` fixture handles cleanup automatically. `AsyncMock` matches the async CRUD interface.

## Writing Integration Tests

Integration tests use the real database via `client` and `db_session`. The session-based auth flow needs to be honored — `httpx.AsyncClient` keeps cookies between calls, so log in once and reuse the client.

```python
# tests/integration/api/test_users.py
import pytest

from src.modules.user.service import UserService
from tests.helpers.factories import build_user_create_payload


@pytest.mark.integration
async def test_register_login_and_fetch_me(client, db_session):
    # Register
    payload = build_user_create_payload(email="alice@example.com", username="alice")
    register_response = await client.post("/api/v1/users/", json=payload)
    assert register_response.status_code == 201
    user_data = register_response.json()
    assert user_data["username"] == "alice"

    # Log in — sets session cookie on the client
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": payload["password"]},
    )
    assert login_response.status_code == 200

    # Authenticated request reuses the cookie automatically
    me_response = await client.get("/api/v1/users/me/")
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "alice"
```

A small factory to keep payloads readable:

```python
# tests/helpers/factories.py
from faker import Faker

fake = Faker()


def build_user_create_payload(**overrides) -> dict:
    return {
        "name": fake.name(),
        "username": fake.user_name(),
        "email": fake.email(),
        "password": "TestPass123!",
        **overrides,
    }
```

### Authenticating as a Specific User

Because session auth is cookie-based, the client retains the session for subsequent requests. For tests that need a logged-in superuser without going through the registration flow, seed a superuser directly via the service:

```python
# tests/conftest.py (additional fixture)
@pytest_asyncio.fixture
async def superuser_client(client, db_session):
    service = UserService()
    await service.create(
        payload={
            "name": "Super",
            "username": "super",
            "email": "super@test.com",
            "password": "SuperPass123!",
        },
        db=db_session,
    )
    # Manually flip is_superuser via crud_users.update if your service doesn't expose it
    await db_session.commit()

    await client.post("/api/v1/auth/login",
                      json={"username": "super", "password": "SuperPass123!"})
    yield client
```

Then `superuser_client` is a logged-in `AsyncClient` for any test that needs admin access.

### Resetting the Session Between Tests

By default, `httpx.AsyncClient` carries cookies for the lifetime of the client fixture. Since `client` is function-scoped, each test starts with no session. If you ever need to log out mid-test, call `await client.post("/api/v1/auth/logout/")` or clear cookies via `client.cookies.clear()`.

## CSRF in Tests

If `CSRF_ENABLED=true` (the default), state-changing requests need a CSRF token. The boilerplate's CSRF flow uses double-submit cookies — the server sets a cookie, and you echo the value back in a header.

Either:

- **Disable CSRF in the test environment** by setting `CSRF_ENABLED=false` in the test fixture. Quick and pragmatic for service-layer integration tests where CSRF isn't the focus.
- **Honor the flow** for tests that need to assert it works:
  ```python
  # Hit a GET first so the server sets the CSRF cookie
  await client.get("/api/v1/auth/me/")  # any safe endpoint
  csrf_token = client.cookies["csrf_token"]   # cookie name from your config
  response = await client.post(
      "/api/v1/widgets/",
      json={...},
      headers={"X-CSRF-Token": csrf_token},
  )
  ```

See [Authentication → Sessions](authentication/sessions.md) for the CSRF specifics.

## Testing Cached Endpoints

The `@cache` decorator is process-aware: in tests, it talks to whichever cache backend `CACHE_BACKEND` points at. Two strategies:

- **Disable caching** — `CACHE_ENABLED=false` in the test environment. Simplest. The decorator becomes a no-op.
- **Use a local Redis** — point `CACHE_REDIS_HOST` at `localhost` (or a testcontainer). Useful when the test specifically asserts caching behavior.

For most unit/integration tests, disable. Add explicit cache tests under `tests/integration/` only when you need to verify invalidation behavior.

## Testing Background Tasks

Taskiq tasks shouldn't actually run during tests. Use Taskiq's `InMemoryBroker` to make `.kiq()` calls execute synchronously:

```python
# tests/conftest.py (additional)
from taskiq import InMemoryBroker

from infrastructure.taskiq import default_broker as real_broker

@pytest_asyncio.fixture(autouse=True)
async def in_memory_broker(monkeypatch):
    test_broker = InMemoryBroker()
    monkeypatch.setattr("infrastructure.taskiq.brokers.default_broker", test_broker)
    monkeypatch.setattr("infrastructure.taskiq.default_broker", test_broker)
    yield test_broker
```

Now `await my_task.kiq(...)` runs the task body in the test process. For tests that specifically assert "the task was scheduled" without running it, swap to a mock broker that records calls instead.

## Running the Suite

```bash
cd backend

# Run everything
uv run pytest

# Just unit tests (skip the slower integration ones)
uv run pytest -m unit

# Just integration tests
uv run pytest -m integration

# Stop on first failure
uv run pytest -x

# Keep running on failures, show output for tests matching a name
uv run pytest -k "user_login" -v

# Parallel via pytest-xdist
uv run pytest -n auto

# With coverage (after `uv add --dev pytest-cov`)
uv run pytest --cov=src --cov-report=term-missing
```

## Continuous Integration

The repo's `.github/workflows/tests.yml` runs the test suite on PRs (along with linting and type-checking workflows). All three workflows pin the working directory to `backend/` so the same `uv run pytest` works there as locally.

CI runs in a clean image, which means:

- **No Docker access by default** — testcontainers needs `docker` available. Either:
  - Use the `services:` block in the workflow to start a Postgres container, then point your test conftest at it via env vars
  - Or skip integration tests in CI and run them manually before each release
- **Connections to localhost are sandboxed** — anything connecting outside the runner needs explicit network setup

For most teams, running unit tests in CI and integration tests locally / on a periodic schedule is enough.

## Common Mistakes

### "My test isn't actually using the test database"

Check that `app.dependency_overrides[async_session] = ...` matches the **same callable** the routes depend on. If a route does `Depends(some_other_db_dep)`, your override of `async_session` won't take effect. Look at the route's source.

### "Tests pass individually but fail when run together"

The most common cause: shared state in the database between tests. Either:

- Make every test fixture roll back at the end (the `db_session` fixture above does)
- Use `truncate` between tests instead of `create_all` / `drop_all` (faster on big schemas)

### "Async tests hang"

Almost always missing `asyncio_mode = "auto"` in `pyproject.toml`, or a fixture that's `async def` but not `pytest_asyncio.fixture`-decorated. Both must match.

### "Cookies aren't persisting between test calls"

`httpx.AsyncClient` only keeps cookies if both calls go through the **same** client instance. If you create a new `AsyncClient` per request, you lose the session. Use the fixture client.

### "FastCRUD returns dicts, not models, in tests too"

Yes — that's the design. Don't try to `assert isinstance(result, Widget)`. Assert on dict keys: `assert result["name"] == "..."`.

### "Test database has stale schema after model changes"

If you're using the `Base.metadata.create_all` shortcut (as in the conftest above), the schema rebuilds on every session. If you've added a fixture that rebuilds at module scope, restart the test session. For long-running test databases, run Alembic migrations in the fixture instead.

## Key Files

| Component                | Location                                                    |
|--------------------------|-------------------------------------------------------------|
| Pytest config            | `backend/pyproject.toml` (`[tool.pytest.ini_options]`)      |
| Test root                | `tests/`                                                    |
| Module under test (refs) | `backend/src/modules/user/`, `backend/src/modules/tier/`    |
| Settings (test env)      | `backend/src/infrastructure/config/settings.py`             |
| Models / `Base`          | `backend/src/infrastructure/database/models.py`             |

## Next Steps

- **[Development](development.md)** — broader development workflow
- **[Production](production.md)** — what changes when shipping the test suite to CI
- **[Authentication → Sessions](authentication/sessions.md)** — full session/CSRF flow you'll exercise in tests
