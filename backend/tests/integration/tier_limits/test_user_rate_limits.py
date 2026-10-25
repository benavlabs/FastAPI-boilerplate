"""The limits that follow from a user's tier, read through the user paths."""

import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.rate_limit.crud import crud_rate_limits
from src.modules.rate_limit.models import RateLimit
from src.modules.tier.crud import crud_tiers

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.asyncio


async def test_get_user_rate_limits(auth_client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """Test retrieval of user's rate limits."""
    logger.info("Testing user rate limits retrieval")
    response = await auth_client.get(f"/api/v1/users/{test_user['username']}/rate-limits")

    assert response.status_code == 200
    data = response.json()
    assert "rate_limits" in data


async def test_a_deleted_tier_brings_no_limits(
    auth_client: AsyncClient, db_session: AsyncSession, tiered_user: dict, test_tier: dict
):
    """A tier a soft delete took out applies to nobody, however a user came to point at it."""
    db_session.add(RateLimit(tier_id=test_tier["id"], name="listing", path="/api/v1/users/", limit=2, period=3600))
    await db_session.commit()
    await crud_tiers.delete(db=db_session, name=test_tier["name"])

    response = await auth_client.get(f"/api/v1/users/{tiered_user['username']}/rate-limits")

    assert response.status_code == 200
    body = response.json()
    assert body["rate_limits"] == []
    assert body["tier"] is None


async def test_a_deleted_rate_limit_is_left_out(
    auth_client: AsyncClient, db_session: AsyncSession, tiered_user: dict, test_tier: dict
):
    db_session.add(RateLimit(tier_id=test_tier["id"], name="live", path="/api/v1/users/", limit=2, period=3600))
    gone = RateLimit(tier_id=test_tier["id"], name="gone", path="/api/v1/tiers/", limit=5, period=3600)
    db_session.add(gone)
    await db_session.commit()
    await crud_rate_limits.delete(db=db_session, name="gone")

    response = await auth_client.get(f"/api/v1/users/{tiered_user['username']}/rate-limits")

    assert response.status_code == 200
    assert [limit["name"] for limit in response.json()["rate_limits"]] == ["live"]
