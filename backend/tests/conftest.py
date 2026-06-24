import os

# Configure the environment BEFORE importing anything from ``src``: the crudauth
# ``auth`` singleton is constructed at import time and reads ``SESSION_BACKEND``,
# so it must be set to the in-memory backend (no Redis) before that import runs.
os.environ.setdefault("SESSION_BACKEND", "memory")
# Tests run over http (base_url http://test), so the session/CSRF cookies must not be
# Secure-only or httpx won't send them back on follow-up requests.
os.environ.setdefault("SESSION_SECURE_COOKIES", "false")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_tests")
os.environ.setdefault("SQLITE_URI", ":memory:")
os.environ.setdefault("SQLITE_ASYNC_PREFIX", "sqlite+aiosqlite:///")

# Disable the testcontainers Ryuk reaper. Under `pytest -n auto`, each xdist worker
# is a separate process that spins up its own Ryuk container, and Docker Desktop
# chokes mapping all their ports at once ("Port mapping ... port 8080 is not
# available"). Testcontainers' own `with` blocks still clean up on normal exit.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
import redis as syncredis  # noqa: E402
import redis.asyncio as aioredis  # noqa: E402
from crudauth import get_password_hash  # noqa: E402
from faker import Faker  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from testcontainers.core.docker_client import DockerClient  # noqa: E402

# mypy: disable-error-code="import-untyped"
from testcontainers.postgres import PostgresContainer  # noqa: E402

from src.infrastructure.auth.dependencies import get_current_superuser, get_current_user  # noqa: E402
from src.infrastructure.config.settings import Settings, get_settings  # noqa: E402
from src.infrastructure.database.session import Base, async_session  # noqa: E402
from src.interfaces.main import app  # noqa: E402
from src.modules.tier.models import Tier  # noqa: E402
from src.modules.user.models import User  # noqa: E402

TEST_DATABASE_URL = get_settings().DATABASE_URL

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))


def is_docker_running() -> bool:
    try:
        DockerClient()
        return True
    except Exception:
        return False


@pytest_asyncio.fixture(scope="session")
async def pg_container():
    """Create a PostgreSQL container for testing."""
    if not is_docker_running():
        pytest.skip("Docker is required, but not running")

    with PostgresContainer() as pg:
        yield pg


@pytest_asyncio.fixture(scope="function")
async def test_db_url(pg_container):
    """Create a proper asyncpg URL for PostgreSQL."""
    host = pg_container.get_container_host_ip()
    port_to_expose = 5432
    if hasattr(pg_container, "port_to_expose"):
        port_to_expose = pg_container.port_to_expose
    port = pg_container.get_exposed_port(port_to_expose)

    db = "test"
    user = "test"
    password = "test"
    if hasattr(pg_container, "POSTGRES_USER"):
        user = pg_container.POSTGRES_USER
    if hasattr(pg_container, "POSTGRES_PASSWORD"):
        password = pg_container.POSTGRES_PASSWORD
    if hasattr(pg_container, "POSTGRES_DB"):
        db = pg_container.POSTGRES_DB

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


@pytest_asyncio.fixture(scope="function")
async def test_db_engine(test_db_url):
    """Create a SQLAlchemy engine for testing."""
    engine = create_async_engine(test_db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_db(test_db_engine):
    """Create a test database session."""
    test_session = sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)
    async with test_session() as session:  # type: ignore
        yield session


@pytest_asyncio.fixture(scope="function")
async def db_session(test_db):
    """Alias for test_db."""
    yield test_db


@pytest_asyncio.fixture(scope="function")
async def client(test_db):
    """Create a test client with an overridden database session."""
    app.dependency_overrides = {}

    async def override_get_db():
        yield test_db

    app.dependency_overrides[async_session] = override_get_db

    os.environ["POSTGRES_SERVER"] = "localhost"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides = {}


@pytest_asyncio.fixture
async def test_tier(db_session: AsyncSession):
    """Create a test tier."""
    tier = Tier(name="free", description="Free tier")
    db_session.add(tier)
    await db_session.commit()
    return {"id": tier.id, "name": tier.name}


@pytest_asyncio.fixture
async def second_test_tier(db_session: AsyncSession):
    """Create a second test tier."""
    tier = Tier(name="premium", description="Premium tier")
    db_session.add(tier)
    await db_session.commit()
    return {"id": tier.id, "name": tier.name}


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_tier: dict):
    """Create a test user."""
    fake = Faker()
    user = User(
        name=fake.name(),
        username=f"u{fake.random_int(10000, 99999)}",
        email=fake.email(),
        hashed_password=get_password_hash("Password123!"),
        is_superuser=False,
        tier_id=test_tier["id"],
        profile_image_url="https://example.com/test.jpg",
    )
    db_session.add(user)
    await db_session.commit()
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,
        "tier_id": user.tier_id,
        "password": "Password123!",
        "profile_image_url": user.profile_image_url,
    }


@pytest_asyncio.fixture
async def test_user_2(db_session: AsyncSession, test_tier: dict):
    """Second test user for permission tests."""
    fake = Faker()
    user = User(
        name=fake.name(),
        username=f"u{fake.random_int(10000, 99999)}",
        email=fake.email(),
        hashed_password=get_password_hash("Password123!"),
        is_superuser=False,
        tier_id=test_tier["id"],
        profile_image_url="https://example.com/test2.jpg",
    )
    db_session.add(user)
    await db_session.commit()
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,
        "tier_id": user.tier_id,
        "password": "Password123!",
    }


@pytest_asyncio.fixture
async def test_superuser(db_session: AsyncSession, test_tier: dict):
    """Create a test superuser."""
    fake = Faker()
    user = User(
        name=fake.name(),
        username=f"su{fake.random_int(10000, 99999)}",
        email=fake.email(),
        hashed_password=get_password_hash("SuperuserPass123!"),
        is_superuser=True,
        tier_id=test_tier["id"],
        profile_image_url="https://example.com/superuser.jpg",
    )
    db_session.add(user)
    await db_session.commit()
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,
        "tier_id": user.tier_id,
        "password": "SuperuserPass123!",
    }


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, test_user: dict):
    """Authenticated test client (regular user) — overrides get_current_user dependency."""

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    return client


@pytest_asyncio.fixture
async def auth_client_2(client: AsyncClient, test_user_2: dict):
    """Authenticated test client for second user."""

    async def override_get_current_user():
        return test_user_2

    app.dependency_overrides[get_current_user] = override_get_current_user
    return client


@pytest_asyncio.fixture
async def superuser_auth_client(client: AsyncClient, test_superuser: dict):
    """Authenticated test client (superuser)."""

    async def override_get_current_user():
        return test_superuser

    async def override_get_current_superuser():
        return test_superuser

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_superuser] = override_get_current_superuser
    return client


@pytest.fixture(autouse=True)
def patch_redis_pipeline_for_tests(monkeypatch):
    """Patch Redis pipeline so tests don't need a live Redis."""

    class MockPipeline:
        def __init__(self, *args, **kwargs):
            self.commands = []

        def execute(self, *args, **kwargs):
            return [True for _ in self.commands]

        async def aexecute(self, *args, **kwargs):
            return [True for _ in self.commands]

        def set(self, *args, **kwargs):
            self.commands.append(("set", args, kwargs))
            return self

        def sadd(self, *args, **kwargs):
            self.commands.append(("sadd", args, kwargs))
            return self

        def srem(self, *args, **kwargs):
            self.commands.append(("srem", args, kwargs))
            return self

        def expire(self, *args, **kwargs):
            self.commands.append(("expire", args, kwargs))
            return self

        def delete(self, *args, **kwargs):
            self.commands.append(("delete", args, kwargs))
            return self

    monkeypatch.setattr(aioredis.Redis, "pipeline", MockPipeline)
    monkeypatch.setattr(syncredis.Redis, "pipeline", MockPipeline)


@pytest.fixture
def mock_rate_limit_settings_fail_open():
    """Mock settings with fail_open=True for rate limiter tests."""
    settings = MagicMock(spec=Settings)
    settings.RATE_LIMITER_ENABLED = True
    settings.RATE_LIMITER_FAIL_OPEN = True
    settings.DEFAULT_RATE_LIMIT_LIMIT = 100
    settings.DEFAULT_RATE_LIMIT_PERIOD = 60
    return settings


@pytest.fixture
def mock_rate_limit_settings_fail_closed():
    """Mock settings with fail_open=False for rate limiter tests."""
    settings = MagicMock(spec=Settings)
    settings.RATE_LIMITER_ENABLED = True
    settings.RATE_LIMITER_FAIL_OPEN = False
    settings.DEFAULT_RATE_LIMIT_LIMIT = 100
    settings.DEFAULT_RATE_LIMIT_PERIOD = 60
    return settings


@pytest.fixture(autouse=True)
def mock_oauth_settings(monkeypatch):
    """Mock OAuth settings for testing."""
    monkeypatch.setenv("OAUTH_REDIRECT_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_ID", "mock-google-client-id")
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_SECRET", "mock-google-client-secret")
    monkeypatch.setenv("OAUTH_GITHUB_CLIENT_ID", "mock-github-client-id")
    monkeypatch.setenv("OAUTH_GITHUB_CLIENT_SECRET", "mock-github-client-secret")
