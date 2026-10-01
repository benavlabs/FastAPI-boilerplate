import logging

import pytest
from crudauth import make_unusable_password
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.user.models import User

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
        "current_password": test_user["password"],
    }

    logger.info(f"Testing successful profile update for user: {username}, user_id: {test_user['id']}")
    response = await auth_client.patch(f"/api/v1/users/{username}", json=update_data)

    if response.status_code != 200:
        logger.error(f"Response status: {response.status_code}, body: {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["message"] == "User updated successfully"

    stored = await db_session.get_one(User, test_user["id"])
    await db_session.refresh(stored)
    assert stored.name == update_data["name"]
    assert stored.email == update_data["email"]


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
    assert data["detail"] == "You don't have permission for this action."


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
    update_data = {"email": other_user_data["email"], "current_password": test_user["password"]}

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


@pytest.mark.parametrize("field", ["name", "username", "profile_image_url"])
async def test_an_explicit_null_is_refused_not_a_server_error(auth_client: AsyncClient, test_user: dict, field: str):
    """A client sending null for a column the row requires gets told, not a 500."""
    response = await auth_client.patch(f"/api/v1/users/{test_user['username']}", json={field: None})

    assert response.status_code == 422


class TestAnEmailChangeIsReauthenticated:
    """What the PATCH route requires before an account's address moves."""

    async def test_without_the_current_password_it_is_refused(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        response = await auth_client.patch(f"/api/v1/users/{test_user['username']}", json={"email": "attacker@example.com"})

        assert response.status_code == 403
        assert response.json()["detail"] == "Confirm this change with your current password."
        stored = await db_session.get_one(User, test_user["id"])
        await db_session.refresh(stored)
        assert stored.email == test_user["email"]

    async def test_with_the_wrong_password_it_is_refused(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        response = await auth_client.patch(
            f"/api/v1/users/{test_user['username']}",
            json={"email": "attacker@example.com", "current_password": "NotTheOne123!"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Confirm this change with your current password."
        stored = await db_session.get_one(User, test_user["id"])
        await db_session.refresh(stored)
        assert stored.email == test_user["email"]

    async def test_with_the_current_password_it_succeeds_and_clears_the_verification(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        await db_session.execute(update(User).where(User.id == test_user["id"]).values(email_verified=True))
        await db_session.commit()

        response = await auth_client.patch(
            f"/api/v1/users/{test_user['username']}",
            json={"email": "moved@example.com", "current_password": test_user["password"]},
        )

        assert response.status_code == 200
        stored = await db_session.get_one(User, test_user["id"])
        await db_session.refresh(stored)
        assert stored.email == "moved@example.com"
        assert stored.email_verified is False

    async def test_an_account_that_signs_in_with_a_provider_cannot_change_its_address(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        await db_session.execute(
            update(User).where(User.id == test_user["id"]).values(hashed_password=make_unusable_password())
        )
        await db_session.commit()

        response = await auth_client.patch(
            f"/api/v1/users/{test_user['username']}",
            json={"email": "moved@example.com", "current_password": test_user["password"]},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "This account signs in with a provider, so its address can't be changed here."
        stored = await db_session.get_one(User, test_user["id"])
        await db_session.refresh(stored)
        assert stored.email == test_user["email"]

    async def test_another_field_needs_no_password(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: dict):
        response = await auth_client.patch(f"/api/v1/users/{test_user['username']}", json={"name": "Renamed Only"})

        assert response.status_code == 200
        stored = await db_session.get_one(User, test_user["id"])
        await db_session.refresh(stored)
        assert stored.name == "Renamed Only"

    async def test_the_same_address_again_needs_no_password(self, auth_client: AsyncClient, test_user: dict):
        response = await auth_client.patch(f"/api/v1/users/{test_user['username']}", json={"email": test_user["email"]})

        assert response.status_code == 200

    async def test_the_password_is_never_stored_or_echoed(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        response = await auth_client.patch(
            f"/api/v1/users/{test_user['username']}",
            json={"email": "kept@example.com", "current_password": test_user["password"]},
        )

        assert response.status_code == 200
        assert test_user["password"] not in response.text
        stored = await db_session.get_one(User, test_user["id"])
        await db_session.refresh(stored)
        assert stored.hashed_password.startswith("$2b$")
