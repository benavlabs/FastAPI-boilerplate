import asyncio
import logging
import traceback
import uuid
from collections.abc import AsyncGenerator

import pytest
from faker import Faker
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database.session import async_session
from src.interfaces.main import app
from src.modules.user.crud import crud_users
from src.modules.user.exceptions import UserExistsError
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

    assert response.status_code == 409
    assert response.json()["detail"] == "A user with this email or username already exists."


async def test_create_user_duplicate_email(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """Test user creation with duplicate email."""
    user_data = generate_unique_user_data()
    user_data["email"] = test_user["email"]

    logger.info(f"Testing user creation with duplicate email: {user_data['email']}")
    response = await client.post("/api/v1/users/", json=user_data)

    assert response.status_code == 409
    assert response.json()["detail"] == "A user with this email or username already exists."


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


async def test_signup_names_every_missing_class_at_once(client: AsyncClient, db_session: AsyncSession):
    """A password missing several classes reports all of them, not just the first."""
    response = await client.post("/api/v1/users/", json={**generate_unique_user_data(), "password": "password"})

    assert response.status_code == 422
    requirements = {error["ctx"]["requirement"] for error in response.json()["detail"]}
    assert {"uppercase", "digit", "special"} <= requirements


@pytest.mark.parametrize(
    "field, value",
    [
        ("email_verified", True),
        ("google_id", "attacker-google-sub"),
        ("github_id", "attacker-github-id"),
        ("oauth_provider", "google"),
        ("oauth_created_at", "2026-01-01T00:00:00Z"),
        ("oauth_updated_at", "2026-01-01T00:00:00Z"),
    ],
)
async def test_signup_refuses_the_oauth_fields(client: AsyncClient, db_session: AsyncSession, field: str, value):
    """Signing up as verified would pre-claim the address before its owner uses a provider login."""
    payload = {**generate_unique_user_data(), field: value}

    response = await client.post("/api/v1/users/", json=payload)

    assert response.status_code == 422
    stored = await db_session.scalar(select(User).where(User.email == payload["email"]))
    assert stored is None


async def test_signup_leaves_the_address_unverified(client: AsyncClient, db_session: AsyncSession):
    """Only a provider login or a verification email may mark an address verified."""
    payload = generate_unique_user_data()

    response = await client.post("/api/v1/users/", json=payload)

    assert response.status_code == 201
    stored = await db_session.scalar(select(User).where(User.email == payload["email"]))
    assert stored is not None
    assert stored.email_verified is False
    assert stored.google_id is None
    assert stored.oauth_provider is None


@pytest.mark.usefixtures("fresh_login_lockout")
async def test_an_address_typed_in_mixed_case_can_sign_in(client: AsyncClient):
    """crudauth looks accounts up in lowercase, so signup has to store them that way."""
    signup = await client.post(
        "/api/v1/users/",
        json={
            "name": "Mixed Case",
            "username": "mixedcaseuser",
            "email": "Alice@Example.COM",
            "password": "Str1ngst!",
        },
    )
    assert signup.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "Alice@Example.COM", "password": "Str1ngst!"},
    )

    assert login.status_code == 200


async def test_the_same_address_in_another_case_cannot_register_twice(client: AsyncClient):
    first = await client.post(
        "/api/v1/users/",
        json={"name": "First Owner", "username": "firstowner", "email": "owner@example.com", "password": "Str1ngst!"},
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/users/",
        json={"name": "Second Owner", "username": "secondowner", "email": "OWNER@Example.com", "password": "Str1ngst!"},
    )

    assert second.status_code == 409
    assert second.json()["detail"] == "A user with this email or username already exists."


class TestAnAddressTheColumnCannotHold:
    """An email longer than the column is refused before it reaches the database."""

    async def test_a_sixty_character_address_is_refused(self, client: AsyncClient):
        over_the_column = f"{'a' * 48}@example.com"

        response = await client.post("/api/v1/users/", json={**generate_unique_user_data(), "email": over_the_column})

        assert response.status_code == 422
        assert over_the_column not in response.text

    async def test_the_longest_address_the_column_holds_is_accepted(self, client: AsyncClient):
        at_the_column = f"{'a' * 38}@example.com"

        response = await client.post("/api/v1/users/", json={**generate_unique_user_data(), "email": at_the_column})

        assert response.status_code == 201
        assert response.json()["email"] == at_the_column


async def test_a_username_the_checks_missed_is_a_conflict_that_logs_neither_the_hash_nor_the_address(
    client: AsyncClient, db_session: AsyncSession, monkeypatch, caplog
):
    """The unique constraint refuses it, and the statement's parameters stay out of the log."""
    first = generate_unique_user_data()
    assert (await client.post("/api/v1/users/", json=first)).status_code == 201

    async def never_exists(*args, **kwargs):
        return False

    monkeypatch.setattr(crud_users, "exists", never_exists)
    same_username = {**generate_unique_user_data(), "username": first["username"]}

    with caplog.at_level(logging.DEBUG):
        response = await client.post("/api/v1/users/", json=same_username)

    await db_session.rollback()
    stored = (await db_session.execute(select(User).where(User.username == first["username"]))).scalar_one()
    logged = "\n".join(
        record.getMessage() + ("".join(traceback.format_exception(*record.exc_info)) if record.exc_info else "")
        for record in caplog.records
    )

    assert response.status_code == 409
    assert response.json()["detail"] == UserExistsError.public_detail
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert stored.hashed_password not in logged
    assert "$2b$" not in logged
    assert same_username["email"] not in logged


async def test_a_name_carrying_a_nul_is_refused(client: AsyncClient, caplog):
    """A NUL encodes, and Postgres then refuses the whole statement that carries it."""
    with caplog.at_level(logging.WARNING):
        response = await client.post(
            "/api/v1/users/",
            json={"name": "a\u0000b", "username": "nulname", "email": "nul@example.com", "password": "Password123!"},
        )

    assert response.status_code == 422
    assert "holds a NUL character" in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


async def test_a_password_that_is_not_valid_unicode_is_refused(client: AsyncClient, caplog):
    """A lone surrogate reaches the hash as text nothing can encode."""
    with caplog.at_level(logging.WARNING):
        response = await client.post(
            "/api/v1/users/",
            content='{"name": "Surrogate", "username": "surrogate", "email": "s@example.com", "password": "Passw0rd!\\ud800"}',
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert "not valid Unicode" in caplog.text
    assert "Passw0rd" not in caplog.text


@pytest.fixture
async def a_session_per_request(test_db_engine):
    """A client whose requests each get their own session, so they can run at once."""
    sessions = async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)

    async def one_session() -> AsyncGenerator[AsyncSession, None]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[async_session] = one_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides = {}


async def test_signups_racing_for_one_address_give_one_account_and_the_rest_a_conflict(
    a_session_per_request: AsyncClient, test_db_engine, caplog
):
    """Four at once used to answer 201 and three 500s, since each checked the table before inserting."""
    signup = generate_unique_user_data()

    with caplog.at_level(logging.DEBUG):
        answers = await asyncio.gather(*(a_session_per_request.post("/api/v1/users/", json=signup) for _ in range(4)))

    sessions = async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as session:
        stored = (await session.execute(select(User).where(User.email == signup["email"]))).scalars().all()

    assert sorted(answer.status_code for answer in answers) == [201, 409, 409, 409]
    assert len(stored) == 1
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


async def test_signing_up_as_an_address_stored_before_it_was_canonicalised_is_a_conflict(
    client: AsyncClient, db_session: AsyncSession, caplog
):
    """The lookup canonicalises and the row does not, so only ``ix_user_email_lower`` catches it."""
    signup = generate_unique_user_data()
    db_session.add(
        User(
            name="Legacy",
            username=f"legacy{uuid.uuid4().hex[:6]}",
            email=signup["email"].upper(),
            hashed_password="not-a-hash",
        )
    )
    await db_session.commit()

    with caplog.at_level(logging.DEBUG):
        response = await client.post("/api/v1/users/", json=signup)

    after = await client.post("/api/v1/users/", json=generate_unique_user_data())
    stored = (await db_session.execute(select(User).where(User.email.ilike(signup["email"])))).scalars().all()

    assert response.status_code == 409
    assert response.json()["detail"] == UserExistsError.public_detail
    assert after.status_code == 201, "the refused insert left the session unusable"
    assert [row.email for row in stored] == [signup["email"].upper()]
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
