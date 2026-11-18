"""Fixtures of the accounts feature: users, and clients signed in as them."""

import time
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from crudauth import get_password_hash
from crudauth.utils import canonical_email
from faker import Faker
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _signed_in_as(user: dict, db: AsyncSession) -> AsyncIterator[AsyncClient]:
    """A client of its own, signed in as ``user`` through the login route and carrying its CSRF token.

    The address is marked verified first.
    """
    await db.execute(update(User).where(User.id == user["id"]).values(email_verified=True))
    await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as signed_in:
        response = await signed_in.post("/api/v1/auth/login", data={"username": user["username"], "password": user["password"]})
        assert response.status_code == 200, response.text
        signed_in.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        yield signed_in


@pytest_asyncio.fixture
async def auth_client(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, fresh_login_lockout: None
) -> AsyncIterator[AsyncClient]:
    """A client signed in as ``test_user``, with a session of its own.

    It takes ``client`` for the database override that fixture installs: without it the login route
    reaches the app's own database instead of the test one.
    """
    async for signed_in in _signed_in_as(test_user, db_session):
        yield signed_in


@pytest_asyncio.fixture
async def auth_client_2(
    client: AsyncClient, db_session: AsyncSession, test_user_2: dict, fresh_login_lockout: None
) -> AsyncIterator[AsyncClient]:
    """A client signed in as ``test_user_2``, with a session of its own beside ``auth_client``'s.

    It takes ``client`` for the database override that fixture installs: without it the login route
    reaches the app's own database instead of the test one.
    """
    async for signed_in in _signed_in_as(test_user_2, db_session):
        yield signed_in


@pytest_asyncio.fixture
async def superuser_auth_client(
    client: AsyncClient, db_session: AsyncSession, test_superuser: dict, fresh_login_lockout: None
) -> AsyncIterator[AsyncClient]:
    """A client signed in as ``test_superuser``, with a session of its own beside the other two.

    It takes ``client`` for the database override that fixture installs: without it the login route
    reaches the app's own database instead of the test one.
    """
    async for signed_in in _signed_in_as(test_superuser, db_session):
        yield signed_in


@pytest.fixture(autouse=True)
def mock_oauth_settings(monkeypatch):
    """Mock OAuth settings for testing."""
    monkeypatch.setenv("OAUTH_REDIRECT_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_ID", "mock-google-client-id")
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_SECRET", "mock-google-client-secret")
    monkeypatch.setenv("OAUTH_GITHUB_CLIENT_ID", "mock-github-client-id")
    monkeypatch.setenv("OAUTH_GITHUB_CLIENT_SECRET", "mock-github-client-secret")


TEST_CLIENT_IP = "127.0.0.1"
PASSWORD_ATTEMPT_ACTION = "change_password"


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


RECOVERY_ACTIONS = ("email_verify_request", "password_reset_request", "email_change_request")


async def reset_recovery_budgets(*addresses: str) -> None:
    """Clear the recovery-flow budgets: the test client's per-address caps and its per-IP ones.

    Both are counted in the process the suite runs in, so they carry from test to test.
    """
    for action in RECOVERY_ACTIONS:
        limit = crud_auth.rate_limits[action]
        window = int(time.time()) // limit.seconds * limit.seconds
        per_address = [f"email:{action}:{canonical_email(address)}" for address in addresses]
        per_ip = f"ratelimit:{action}:{TEST_CLIENT_IP}"

        await _reset_limiter_keys(per_ip, f"{per_ip}:{window}", *per_address)


@pytest_asyncio.fixture
async def fresh_login_lockout():
    """Clear the login lockout counted against the test client's address."""
    await _reset_limiter_keys(
        f"login:ip:{TEST_CLIENT_IP}",
        f"login:lock:ip:{TEST_CLIENT_IP}",
        f"login:rounds:ip:{TEST_CLIENT_IP}",
    )
