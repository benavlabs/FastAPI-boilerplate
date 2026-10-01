"""The limit a caller's tier configures for a path, end to end."""

import itertools
import time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.setup import auth
from src.infrastructure.config.settings import settings
from src.modules.rate_limit.models import RateLimit

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

_addresses = (f"198.51.100.{n}" for n in itertools.count(100))


async def _reset(key: str, period: int) -> None:
    """Clear a caller's counter for a path, including the current window's key."""
    limiter = auth.rate_limiter
    assert limiter is not None
    now = int(time.time())
    await limiter.reset(key)
    await limiter.reset(f"{key}:{now - now % period}")


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
    await _reset(f"ratelimit:api:user:{tiered_user['id']}:{path}", 3600)

    responses = [await client.get(path) for _ in range(3)]
    default_path = await client.get("/api/v1/users/me")

    assert [response.status_code for response in responses] == [200, 200, 429]
    assert responses[0].headers["X-RateLimit-Limit"] == "2"
    assert responses[0].headers["X-RateLimit-Remaining"] == "1"
    assert default_path.status_code == 200
    assert default_path.headers["X-RateLimit-Limit"] == "3"


async def test_a_template_row_applies_to_every_path_that_matches_it(
    client: AsyncClient, db_session: AsyncSession, tiered_user: dict, test_user_2: dict, test_tier: dict, limits: dict
):
    """Two usernames are one route, so they share the row's budget."""
    template = "/api/v1/users/{username}"
    db_session.add(RateLimit(tier_id=test_tier["id"], name="user_lookup", path=template, limit=2, period=3600))
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/login", data={"username": tiered_user["username"], "password": tiered_user["password"]}
    )
    assert login.status_code == 200
    await _reset(f"ratelimit:api:user:{tiered_user['id']}:{template}", 3600)

    first = await client.get(f"/api/v1/users/{tiered_user['username']}")
    second = await client.get(f"/api/v1/users/{test_user_2['username']}")
    third = await client.get(f"/api/v1/users/{tiered_user['username']}")

    assert [first.status_code, second.status_code, third.status_code] == [200, 200, 429]
    assert first.headers["X-RateLimit-Limit"] == "2"
    assert second.headers["X-RateLimit-Remaining"] == "0"


async def test_a_soft_deleted_row_no_longer_applies(
    client: AsyncClient, db_session: AsyncSession, tiered_user: dict, test_tier: dict, limits: dict
):
    path = "/api/v1/tiers/"
    row = RateLimit(tier_id=test_tier["id"], name="tiers_listing", path=path, limit=1, period=3600)
    row.is_deleted = True
    db_session.add(row)
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/login", data={"username": tiered_user["username"], "password": tiered_user["password"]}
    )
    assert login.status_code == 200
    await _reset(f"ratelimit:api:user:{tiered_user['id']}:{path}", 3600)

    response = await client.get(path)

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "3"
