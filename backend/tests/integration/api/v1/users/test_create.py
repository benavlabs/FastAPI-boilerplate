import logging
import uuid

import pytest
from faker import Faker
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.user.models import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

fake = Faker()
pytestmark = pytest.mark.asyncio


def generate_unique_user_data(prefix="user"):
    """Generate unique user data for testing."""
    unique_id = uuid.uuid4().hex[:6]
    return {
        "name": f"Test {prefix.capitalize()} {unique_id}",
        "username": f"{prefix}{unique_id}",
        "email": f"{prefix}.user.{unique_id}@example.com",
        "password": "Password123!",
    }


async def test_create_user_success(client: AsyncClient, db_session: AsyncSession):
    """Test successful user creation."""
    user_data = generate_unique_user_data()

    logger.info(f"Testing user creation with username: {user_data['username']}")
    response = await client.post("/api/v1/users/", json=user_data)

    assert response.status_code == 201
    data = response.json()
    assert data["username"] == user_data["username"]
    assert data["email"] == user_data["email"]
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data


async def test_create_user_invalid_email(client: AsyncClient, db_session: AsyncSession):
    """Test user creation with invalid email format."""
    user_data = generate_unique_user_data()
    user_data["email"] = "invalid-email"

    logger.info("Testing user creation with invalid email")
    response = await client.post("/api/v1/users/", json=user_data)

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


async def test_create_user_duplicate_username(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """Test user creation with duplicate username."""
    user_data = generate_unique_user_data()
    user_data["username"] = test_user["username"]

    logger.info(f"Testing user creation with duplicate username: {user_data['username']}")
    response = await client.post("/api/v1/users/", json=user_data)

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


async def test_create_user_duplicate_email(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """Test user creation with duplicate email."""
    user_data = generate_unique_user_data()
    user_data["email"] = test_user["email"]

    logger.info(f"Testing user creation with duplicate email: {user_data['email']}")
    response = await client.post("/api/v1/users/", json=user_data)

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


async def test_create_superuser(superuser_auth_client: AsyncClient, db_session: AsyncSession):
    """Test superuser creating another superuser via API and database."""
    user_data = generate_unique_user_data("admin")

    logger.info(f"Testing user creation with username: {user_data['username']}")
    response = await superuser_auth_client.post("/api/v1/users/", json=user_data)

    assert response.status_code == 201
    created_user = response.json()

    user_in_db = await db_session.get(User, created_user["id"])
    assert user_in_db is not None, "User not found in database"
    user_in_db.is_superuser = True
    await db_session.commit()
    await db_session.refresh(user_in_db)

    assert user_in_db.is_superuser is True


@pytest.mark.parametrize(
    ("password", "requirement"),
    [
        ("password123!", "uppercase"),
        ("PASSWORD123!", "lowercase"),
        ("Password!!!!", "digit"),
        ("Password1234", "special"),
        ("Senhaé123", "special"),
    ],
)
async def test_signup_rejects_a_password_missing_a_required_class(
    client: AsyncClient, db_session: AsyncSession, password: str, requirement: str
):
    """The policy names every class a password lacks; an accented letter is a letter, not a special."""
    user_data = {**generate_unique_user_data(), "password": password}

    response = await client.post("/api/v1/users/", json=user_data)

    assert response.status_code == 422
    requirements = [error["ctx"]["requirement"] for error in response.json()["detail"]]
    assert requirement in requirements
    assert password not in response.text


async def test_signup_rejects_a_short_password(client: AsyncClient, db_session: AsyncSession):
    response = await client.post("/api/v1/users/", json={**generate_unique_user_data(), "password": "Pa1!"})

    assert response.status_code == 422


async def test_signup_accepts_a_non_latin_password(client: AsyncClient, db_session: AsyncSession):
    """Character classes are Unicode-aware, so a Cyrillic password has letters of both cases."""
    response = await client.post("/api/v1/users/", json={**generate_unique_user_data(), "password": "Пароль1!"})

    assert response.status_code == 201
