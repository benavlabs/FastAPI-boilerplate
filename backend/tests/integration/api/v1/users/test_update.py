import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.common.constants import GENERIC_ERROR_MESSAGE

from .test_create import generate_unique_user_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


async def test_update_user_profile_success(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    """Test successful profile update."""
    username = test_user["username"]
    update_data = {
        "name": "Updated Name",
        "email": "updated.email@example.com",
        "profile_image_url": "https://example.com/new-image.jpg",
    }

    logger.info(f"Testing successful profile update for user: {username}, user_id: {test_user['id']}")
    response = await auth_client.patch(f"/api/v1/users/{username}", json=update_data)

    if response.status_code != 200:
        logger.error(f"Response status: {response.status_code}, body: {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["message"] == "User updated successfully"

    get_response = await auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 200
    user_data = get_response.json()
    assert user_data["name"] == update_data["name"]
    assert user_data["email"] == update_data["email"]


async def test_update_user_profile_invalid_email(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    """Test update with invalid email format."""
    username = test_user["username"]
    update_data = {"email": "invalid-email"}

    logger.info(f"Testing invalid email update for user: {username}")
    response = await auth_client.patch(f"/api/v1/users/{username}", json=update_data)

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


async def test_update_user_profile_unauthorized(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """Test update without authentication."""
    username = test_user["username"]
    update_data = {"name": "Unauthorized Update"}

    logger.info("Testing unauthorized profile update")
    response = await client.patch(f"/api/v1/users/{username}", json=update_data)

    assert response.status_code == 401
    data = response.json()
    assert "not authenticated" in data["detail"].lower()


async def test_update_user_profile_wrong_user(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    """Test that users cannot update other users' profiles."""
    other_user_data = generate_unique_user_data("other")
    create_response = await auth_client.post("/api/v1/users/", json=other_user_data)
    assert create_response.status_code == 201
    other_username = other_user_data["username"]

    update_data = {"name": "Unauthorized Update"}
    response = await auth_client.patch(f"/api/v1/users/{other_username}", json=update_data)

    assert response.status_code == 403
    data = response.json()
    assert data["detail"] == GENERIC_ERROR_MESSAGE


async def test_update_user_profile_duplicate_email(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    """Test update with duplicate email fails."""
    other_user_data = generate_unique_user_data("other")
    create_response = await auth_client.post("/api/v1/users/", json=other_user_data)
    assert create_response.status_code == 201

    username = test_user["username"]
    update_data = {"email": other_user_data["email"]}

    logger.info(f"Testing duplicate email update for user: {username}")
    response = await auth_client.patch(f"/api/v1/users/{username}", json=update_data)

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


async def test_update_user_profile_duplicate_username(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    """Test update with duplicate username fails."""
    other_user_data = generate_unique_user_data("other")
    create_response = await auth_client.post("/api/v1/users/", json=other_user_data)
    assert create_response.status_code == 201

    username = test_user["username"]
    update_data = {"username": other_user_data["username"]}

    logger.info(f"Testing duplicate username update for user: {username}")
    response = await auth_client.patch(f"/api/v1/users/{username}", json=update_data)

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


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
