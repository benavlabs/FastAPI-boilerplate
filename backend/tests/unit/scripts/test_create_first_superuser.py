"""Seeding a superuser: only from complete configuration, and never by promotion."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import scripts.create_first_superuser as script
from scripts.create_first_superuser import SeedError, create_first_superuser
from src.infrastructure.config.settings import settings
from src.modules.user.crud import crud_users

pytestmark = pytest.mark.asyncio

COMPLETE = {
    "ADMIN_NAME": "Admin User",
    "ADMIN_EMAIL": "admin@example.com",
    "ADMIN_USERNAME": "seededadmin",
    "ADMIN_PASSWORD": "Str0ngAdmin!",
}


@pytest.fixture
def admin_environment(monkeypatch, db_session: AsyncSession):
    """Complete admin settings, and the seeder writing through the test session."""
    for name, value in COMPLETE.items():
        monkeypatch.setattr(settings, name, value)

    class _Session:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(script, "local_session", _Session)


@pytest.mark.parametrize("missing", sorted(COMPLETE))
async def test_incomplete_configuration_refuses_to_seed(admin_environment, monkeypatch, missing: str):
    """A missing setting must never fall back to a credential someone could guess."""
    monkeypatch.setattr(settings, missing, "")

    with pytest.raises(SeedError, match="ADMIN_"):
        await create_first_superuser()


async def test_an_existing_account_on_that_address_is_not_promoted(
    admin_environment, db_session: AsyncSession, test_user: dict
):
    """Whoever registered the address first may not be the operator."""
    await crud_users.update(db=db_session, object={"email": COMPLETE["ADMIN_EMAIL"]}, id=test_user["id"])

    with pytest.raises(SeedError, match="not a superuser"):
        await create_first_superuser()

    untouched = await crud_users.get(db=db_session, id=test_user["id"])
    assert untouched["is_superuser"] is False


async def test_a_complete_configuration_seeds_a_superuser(admin_environment, db_session: AsyncSession):
    await create_first_superuser()

    seeded = await crud_users.get(db=db_session, email=COMPLETE["ADMIN_EMAIL"])
    assert seeded["is_superuser"] is True
    assert seeded["username"] == COMPLETE["ADMIN_USERNAME"]


async def test_seeding_twice_leaves_the_superuser_alone(admin_environment, db_session: AsyncSession):
    await create_first_superuser()
    await create_first_superuser()

    seeded = await crud_users.get(db=db_session, email=COMPLETE["ADMIN_EMAIL"])
    assert seeded["is_superuser"] is True


async def test_a_mixed_case_address_seeds_once_and_is_then_found(admin_environment, monkeypatch, db_session: AsyncSession):
    """Addresses are stored canonically, so the lookup has to canonicalise too."""
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "Admin@Example.COM")

    await create_first_superuser()
    await create_first_superuser()

    seeded = await crud_users.get(db=db_session, email="admin@example.com")
    assert seeded["is_superuser"] is True
    assert await crud_users.count(db=db_session, email="admin@example.com") == 1


async def test_a_mixed_case_address_held_by_a_plain_user_is_refused(
    admin_environment, monkeypatch, db_session: AsyncSession, test_user: dict
):
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "Admin@Example.COM")
    await crud_users.update(db=db_session, object={"email": "admin@example.com"}, id=test_user["id"])

    with pytest.raises(SeedError, match="not a superuser"):
        await create_first_superuser()


async def test_a_weak_password_is_reported_without_a_traceback(admin_environment, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "short")

    with pytest.raises(SeedError, match="ADMIN_PASSWORD doesn't meet the password policy") as failure:
        await create_first_superuser()

    assert "Traceback" not in str(failure.value)


async def test_a_taken_username_is_reported_as_a_seed_failure(
    admin_environment, monkeypatch, db_session: AsyncSession, test_user: dict
):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", test_user["username"])

    with pytest.raises(SeedError, match="Could not seed the superuser"):
        await create_first_superuser()
