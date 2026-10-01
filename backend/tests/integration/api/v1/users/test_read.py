import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


async def test_get_user_by_username_success(auth_client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """Test successful retrieval of a user by username."""
    logger.info("Testing successful user retrieval by username")
    username = test_user["username"]
    response = await auth_client.get(f"/api/v1/users/{username}")

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == username
    assert "id" in data
    assert "name" in data
    assert "email" not in data


async def test_get_user_by_username_not_found(auth_client: AsyncClient, db_session: AsyncSession):
    """Test 404 when user not found."""
    logger.info("Testing 404 when user not found")
    response = await auth_client.get("/api/v1/users/nonexistentuser")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


async def test_get_users_unauthorized(client: AsyncClient, db_session: AsyncSession):
    """Test that unauthorized users cannot access users list."""
    logger.info("Testing unauthorized access to users list")
    response = await client.get("/api/v1/users/")

    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


async def test_get_users_superuser_success(superuser_auth_client: AsyncClient, db_session: AsyncSession):
    """Test that superuser can access users list."""
    logger.info("Testing superuser access to users list")
    response = await superuser_auth_client.get("/api/v1/users/")

    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert isinstance(data["data"], list)
    assert "total_count" in data
    assert "page" in data
    assert "items_per_page" in data


async def test_get_users_pagination(superuser_auth_client: AsyncClient, db_session: AsyncSession):
    """Test pagination of users list."""
    logger.info("Testing users list pagination")

    response = await superuser_auth_client.get("/api/v1/users/?page=1&items_per_page=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) <= 5
    assert data["page"] == 1
    assert data["items_per_page"] == 5


async def test_get_current_user_profile(auth_client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """Test retrieval of current user's profile."""
    logger.info("Testing current user profile retrieval")
    response = await auth_client.get("/api/v1/users/me")

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == test_user["username"]
    assert data["email"] == test_user["email"]


async def test_get_user_by_username_requires_authentication(client: AsyncClient, test_user: dict):
    """An anonymous caller can't look anyone up by username."""
    response = await client.get(f"/api/v1/users/{test_user['username']}")

    assert response.status_code == 401


async def test_profile_lookup_never_carries_an_email(auth_client: AsyncClient, test_user_2: dict, db_session: AsyncSession):
    """Looking someone else up returns display fields, never their address.

    Registration is open, so anything this endpoint returns is readable by anyone
    willing to sign up; an email address here would be a directory of addresses.
    """
    response = await auth_client.get(f"/api/v1/users/{test_user_2['username']}")

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == test_user_2["username"]
    assert "email" not in data
    assert "is_superuser" not in data


@pytest.mark.parametrize(
    "username",
    [
        "with_underscore",
        "a" * 25,
    ],
)
async def test_a_username_signup_accepts_can_be_looked_up(client: AsyncClient, auth_client: AsyncClient, username: str):
    """The profile response must describe what the column holds, not a stricter rule."""
    signup = await client.post(
        "/api/v1/users/",
        json={
            "name": "Lookup Target",
            "username": username,
            "email": f"{username}@example.com",
            "password": "Password123!",
        },
    )
    assert signup.status_code == 201

    response = await auth_client.get(f"/api/v1/users/{username}")

    assert response.status_code == 200
    assert response.json()["username"] == username


@pytest.mark.parametrize(
    ("path", "method", "expected"),
    [("/api/v1/users/{username}", "get", {"401", "404"})],
)
async def test_openapi_advertises_the_gate(client: AsyncClient, path: str, method: str, expected: set[str]):
    """A client generated from the schema must know these can be refused."""
    schema = (await client.get("/openapi.json")).json()
    operation = schema["paths"][path][method]

    assert expected <= set(operation["responses"])


async def test_a_profile_carries_the_display_fields_only(auth_client: AsyncClient, test_user: dict):
    """The profile route answers with the four display fields, whatever features are wired."""
    response = await auth_client.get(f"/api/v1/users/{test_user['username']}")

    assert response.status_code == 200
    assert set(response.json()) == {"id", "name", "username", "profile_image_url"}
