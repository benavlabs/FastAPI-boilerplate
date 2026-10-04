"""Fixtures of the accounts feature: users, and clients signed in as them."""

import time

import pytest
import pytest_asyncio
from crudauth import Principal, get_password_hash
from faker import Faker
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.dependencies import (
    get_current_principal,
    get_current_superuser,
    get_current_user,
)
from src.infrastructure.auth.password_attempts import PASSWORD_ATTEMPT_ACTION
from src.infrastructure.auth.setup import auth as crud_auth
from src.interfaces.main import app
from src.modules.user.models import User


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    fake = Faker()
    user = User(
        name=fake.name(),
        username=f"u{fake.random_int(10000, 99999)}",
        email=fake.email(),
        hashed_password=get_password_hash("Password123!"),
        is_superuser=False,
        profile_image_url="https://example.com/test.jpg",
    )
    db_session.add(user)
    await db_session.commit()
    await reset_password_budget(user.id)

    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,
        "password": "Password123!",
        "profile_image_url": user.profile_image_url,
    }


@pytest_asyncio.fixture
async def test_user_2(db_session: AsyncSession):
    """Second test user for permission tests."""
    fake = Faker()
    user = User(
        name=fake.name(),
        username=f"u{fake.random_int(10000, 99999)}",
        email=fake.email(),
        hashed_password=get_password_hash("Password123!"),
        is_superuser=False,
        profile_image_url="https://example.com/test2.jpg",
    )
    db_session.add(user)
    await db_session.commit()
    await reset_password_budget(user.id)

    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,
        "password": "Password123!",
    }


@pytest_asyncio.fixture
async def test_superuser(db_session: AsyncSession):
    """Create a test superuser."""
    fake = Faker()
    user = User(
        name=fake.name(),
        username=f"su{fake.random_int(10000, 99999)}",
        email=fake.email(),
        hashed_password=get_password_hash("SuperuserPass123!"),
        is_superuser=True,
        profile_image_url="https://example.com/superuser.jpg",
    )
    db_session.add(user)
    await db_session.commit()
    await reset_password_budget(user.id)

    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,
        "password": "SuperuserPass123!",
    }


def _principal_for(user: dict) -> Principal:
    """The crudauth principal the session transport would resolve for this user.

    The auth fixtures override the dict-compat dependencies, so anything reading
    the principal directly (permission checks, session routes) needs it too.
    """
    return Principal(
        user_id=user["id"],
        transport="session",
        is_superuser=user.get("is_superuser", False),
        email_verified=True,
    )


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, test_user: dict):
    """Authenticated test client (regular user) — overrides get_current_user dependency."""

    async def override_get_current_user():
        return test_user

    async def override_get_current_principal():
        return _principal_for(test_user)

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_principal] = override_get_current_principal
    return client


@pytest_asyncio.fixture
async def auth_client_2(client: AsyncClient, test_user_2: dict):
    """Authenticated test client for second user."""

    async def override_get_current_user():
        return test_user_2

    async def override_get_current_principal():
        return _principal_for(test_user_2)

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_principal] = override_get_current_principal
    return client


@pytest_asyncio.fixture
async def superuser_auth_client(client: AsyncClient, test_superuser: dict):
    """Authenticated test client (superuser)."""

    async def override_get_current_user():
        return test_superuser

    async def override_get_current_principal():
        return _principal_for(test_superuser)

    async def override_get_current_superuser():
        return test_superuser

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_principal] = override_get_current_principal
    app.dependency_overrides[get_current_superuser] = override_get_current_superuser
    return client


@pytest.fixture(autouse=True)
def mock_oauth_settings(monkeypatch):
    """Mock OAuth settings for testing."""
    monkeypatch.setenv("OAUTH_REDIRECT_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_ID", "mock-google-client-id")
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_SECRET", "mock-google-client-secret")
    monkeypatch.setenv("OAUTH_GITHUB_CLIENT_ID", "mock-github-client-id")
    monkeypatch.setenv("OAUTH_GITHUB_CLIENT_SECRET", "mock-github-client-secret")


TEST_CLIENT_IP = "127.0.0.1"


async def _reset_limiter_keys(*keys: str) -> None:
    """Clear ``keys`` in the limiter, if one is configured."""
    limiter = crud_auth.rate_limiter
    if limiter is None:
        return

    for key in keys:
        await limiter.reset(key)


async def reset_password_budget(user_id: int) -> None:
    """Clear one account's change-password budget, the current window included."""
    limit = crud_auth.rate_limits[PASSWORD_ATTEMPT_ACTION]
    window = int(time.time()) // limit.seconds * limit.seconds
    key = f"ratelimit:{PASSWORD_ATTEMPT_ACTION}:{user_id}"

    await _reset_limiter_keys(key, f"{key}:{window}")


@pytest_asyncio.fixture
async def fresh_login_lockout():
    """Clear the login lockout counted against the test client's address."""
    await _reset_limiter_keys(
        f"login:ip:{TEST_CLIENT_IP}",
        f"login:lock:ip:{TEST_CLIENT_IP}",
        f"login:rounds:ip:{TEST_CLIENT_IP}",
    )
