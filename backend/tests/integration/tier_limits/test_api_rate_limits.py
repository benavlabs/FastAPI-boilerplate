"""The limit a caller's tier configures for a path, end to end."""

import itertools

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.setup import auth
from src.infrastructure.config.settings import settings
from src.modules.rate_limit.models import RateLimit

pytestmark = pytest.mark.asyncio

_addresses = (f"198.51.100.{n}" for n in itertools.count(100))


@pytest.fixture
def limits(monkeypatch):
    """A small default limit, so a tier's own limit is visibly different."""
    monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", True)
    monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_LIMIT", 3)
    monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_PERIOD", 3600)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    return {"X-Forwarded-For": next(_addresses)}


async def test_a_signed_in_user_gets_their_tiers_limit_for_the_path(
    client: AsyncClient, db_session: AsyncSession, tiered_user: dict, test_tier: dict, limits: dict
):
    path = "/api/v1/tiers/"
    db_session.add(RateLimit(tier_id=test_tier["id"], name="tiers_listing", path=path, limit=2, period=3600))
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/login", data={"username": tiered_user["username"], "password": tiered_user["password"]}
    )
    assert login.status_code == 200
    await auth.rate_limiter.reset(f"ratelimit:api:user:{tiered_user['id']}:{path}")

    responses = [await client.get(path) for _ in range(3)]
    default_path = await client.get("/api/v1/users/me")

    assert [response.status_code for response in responses] == [200, 200, 429]
    assert responses[0].headers["X-RateLimit-Limit"] == "2"
    assert responses[0].headers["X-RateLimit-Remaining"] == "1"
    assert default_path.status_code == 200
    assert default_path.headers["X-RateLimit-Limit"] == "3"
