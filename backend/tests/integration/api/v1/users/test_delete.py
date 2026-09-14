import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.common.constants import GENERIC_ERROR_MESSAGE

from .test_create import generate_unique_user_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


async def test_soft_delete_success(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    """Test successful soft deletion of user account."""
    username = test_user["username"]

    logger.info(f"Testing soft deletion for user: {username}")
    response = await auth_client.delete(f"/api/v1/users/{username}")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "User account deactivated"

    get_response = await auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 404


async def test_soft_delete_unauthorized(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    """Test soft deletion without authentication."""
    username = test_user["username"]

    response = await client.delete(f"/api/v1/users/{username}")

    assert response.status_code == 401
    data = response.json()
    assert "not authenticated" in data["detail"].lower()


async def test_soft_delete_wrong_user(
    auth_client: AsyncClient,
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    """Test that users cannot delete other users' accounts."""
    other_user_data = generate_unique_user_data("other")
    create_response = await client.post("/api/v1/users/", json=other_user_data)
    assert create_response.status_code == 201
    other_username = other_user_data["username"]

    response = await auth_client.delete(f"/api/v1/users/{other_username}")

    assert response.status_code == 403
    data = response.json()
    assert data["detail"] == GENERIC_ERROR_MESSAGE


async def test_soft_delete_nonexistent_user(
    auth_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test that deleting a non-existent user returns 403 (permission is checked first)."""
    response = await auth_client.delete("/api/v1/users/nonexistentuser")

    assert response.status_code == 403


async def test_permanent_delete_success(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    """Test successful permanent deletion by superuser."""
    username = test_user["username"]

    logger.info(f"Testing permanent deletion for user: {username}")
    response = await superuser_auth_client.delete(f"/api/v1/users/db/{username}")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "User data anonymized in compliance with GDPR"

    get_response = await superuser_auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 404


async def test_permanent_delete_unauthorized(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    """Test that non-admin users cannot permanently delete accounts."""
    username = test_user["username"]

    response = await auth_client.delete(f"/api/v1/users/db/{username}")

    assert response.status_code == 403
    data = response.json()
    assert "insufficient privileges" in data["detail"].lower()


async def test_permanent_delete_inactive_user(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    """Test permanent deletion of soft-deleted accounts"""
    username = test_user["username"]

    logger.info(f"Testing soft deletion for user: {username}")

    response_soft_delete = await superuser_auth_client.delete(f"/api/v1/users/{username}")

    assert response_soft_delete.status_code == 200
    data_soft = response_soft_delete.json()
    assert data_soft["message"] == "User account deactivated"

    logger.info(f"Testing permanent deletion for user: {username}")

    response_perma_delete = await superuser_auth_client.delete(f"/api/v1/users/db/{username}")
    assert response_perma_delete.status_code == 200
    data_perma = response_perma_delete.json()
    assert data_perma["message"] == "User data anonymized in compliance with GDPR"

    get_response = await superuser_auth_client.get(f"/api/v1/users/active-and-inactive/{username}")
    assert get_response.status_code == 404


async def test_permanent_delete_nonexistent_user(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test permanent deletion of non-existent user."""
    response = await superuser_auth_client.delete("/api/v1/users/db/nonexistentuser")

    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == GENERIC_ERROR_MESSAGE


async def test_delete_cascade_effects(
    auth_client: AsyncClient,
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    """Test cascade effects of user deletion."""
    username = test_user["username"]

    tier_response = await auth_client.get(f"/api/v1/users/{username}/tier")
    assert tier_response.status_code == 200

    rate_limits_response = await auth_client.get(f"/api/v1/users/{username}/rate-limits")
    assert rate_limits_response.status_code == 200

    delete_response = await auth_client.delete(f"/api/v1/users/{username}")
    assert delete_response.status_code == 200

    tier_response = await superuser_auth_client.get(f"/api/v1/users/{username}/tier")
    assert tier_response.status_code == 404

    rate_limits_response = await superuser_auth_client.get(f"/api/v1/users/{username}/rate-limits")
    assert rate_limits_response.status_code == 404
