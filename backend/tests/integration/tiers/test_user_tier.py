"""The tier a user is on, read and changed through the user paths."""

import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.asyncio


async def test_get_user_tier_info(auth_client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """Test retrieval of user's tier information."""
    logger.info("Testing user tier information retrieval")
    response = await auth_client.get(f"/api/v1/users/{test_user['username']}/tier")

    assert response.status_code == 200
    data = response.json()
    assert "tier" in data


async def test_update_user_tier_superuser(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    second_test_tier: dict,
):
    """Test that superuser can update user's tier."""
    username = test_user["username"]
    update_data = {"tier_id": second_test_tier["id"]}

    logger.info(f"Testing tier update by superuser for user: {username}")
    response = await superuser_auth_client.patch(f"/api/v1/users/{username}/tier", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["message"] == "User tier updated successfully"

    get_response = await superuser_auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 200
    user_data = get_response.json()
    assert user_data["tier_id"] == second_test_tier["id"]


async def test_update_user_tier_regular_user(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    second_test_tier: dict,
):
    """Test that regular users cannot update their tier."""
    username = test_user["username"]
    update_data = {"tier_id": second_test_tier["id"]}

    logger.info(f"Testing tier update by regular user: {username}")
    response = await auth_client.patch(f"/api/v1/users/{username}/tier", json=update_data)

    assert response.status_code == 403
    data = response.json()
    assert any(word in data["detail"].lower() for word in ["permission", "privileges", "authorized"])
