"""The limits that follow from a user's tier, read through the user paths."""

import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.asyncio


async def test_get_user_rate_limits(auth_client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """Test retrieval of user's rate limits."""
    logger.info("Testing user rate limits retrieval")
    response = await auth_client.get(f"/api/v1/users/{test_user['username']}/rate-limits")

    assert response.status_code == 200
    data = response.json()
    assert "rate_limits" in data
