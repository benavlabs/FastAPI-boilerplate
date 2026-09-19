"""Per-tier, per-path rate limits on the API routes, through crudauth's limiter."""

import itertools

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.setup import auth
from src.infrastructure.config.settings import settings
from src.modules.rate_limit.models import RateLimit

pytestmark = pytest.mark.asyncio

_addresses = (f"198.51.100.{n}" for n in itertools.count(1))


@pytest.fixture
def limits(monkeypatch):
    """A small default limit, and each test's anonymous caller on its own address."""
    monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", True)
    monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_LIMIT", 3)
    monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_PERIOD", 3600)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    return {"X-Forwarded-For": next(_addresses)}


async def test_the_default_limit_is_enforced(client: AsyncClient, limits: dict):
    statuses = [(await client.get("/api/v1/tiers/", headers=limits)).status_code for _ in range(4)]

    assert statuses[:3] == [401, 401, 401]
    assert statuses[3] == 429


async def test_a_refused_request_still_reports_the_budget_it_spent(client: AsyncClient, limits: dict):
    """A 401 after the limiter counted the request tells the client what it has left."""
    responses = [await client.get("/api/v1/tiers/", headers=limits) for _ in range(4)]

    assert [response.status_code for response in responses] == [401, 401, 401, 429]
    assert [response.headers.get("X-RateLimit-Remaining") for response in responses] == ["2", "1", "0", "0"]
    assert all(response.headers.get("X-RateLimit-Limit") == "3" for response in responses)


async def test_each_path_keeps_its_own_budget(client: AsyncClient, limits: dict):
    """Spending the budget on one route never throttles another."""
    for _ in range(3):
        await client.get("/api/v1/tiers/", headers=limits)

    exhausted = await client.get("/api/v1/tiers/", headers=limits)
    other_path = [(await client.get("/api/v1/rate-limits/", headers=limits)).status_code for _ in range(4)]

    assert exhausted.status_code == 429
    assert other_path[:3] == [401, 401, 401]
    assert other_path[3] == 429


async def test_a_signed_in_user_gets_their_tiers_limit_for_the_path(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_tier: dict, limits: dict
):
    path = "/api/v1/tiers/"
    db_session.add(RateLimit(tier_id=test_tier["id"], name="tiers_listing", path=path, limit=2, period=3600))
    await db_session.commit()
    login = await client.post("/api/v1/auth/login", data={"username": test_user["username"], "password": test_user["password"]})
    assert login.status_code == 200
    await auth.rate_limiter.reset(f"ratelimit:api:user:{test_user['id']}:{path}")

    responses = [await client.get(path) for _ in range(3)]
    default_path = await client.get("/api/v1/users/me")

    assert [response.status_code for response in responses] == [200, 200, 429]
    assert responses[0].headers["X-RateLimit-Limit"] == "2"
    assert responses[0].headers["X-RateLimit-Remaining"] == "1"
    assert default_path.status_code == 200
    assert default_path.headers["X-RateLimit-Limit"] == "3"


async def test_disabling_rate_limits_lets_every_request_through(client: AsyncClient, limits: dict, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", False)

    statuses = [(await client.get("/api/v1/tiers/", headers=limits)).status_code for _ in range(5)]

    assert 429 not in statuses
