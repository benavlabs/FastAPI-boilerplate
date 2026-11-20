"""A new account is given the default tier, whether it signed up with a password or a provider."""

import pytest
from crudauth import NewUserContext
from crudauth.provisioning import resolve_new_user_fields
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.setup import auth
from src.infrastructure.config.settings import settings
from src.modules.tier.models import Tier
from src.modules.user.models import User


def _signup(username: str) -> dict[str, str]:
    return {"name": "New Person", "username": username, "email": f"{username}@example.com", "password": "Password123!"}


async def _signed_up(client: AsyncClient, db: AsyncSession, username: str) -> User:
    response = await client.post("/api/v1/users/", json=_signup(username))
    assert response.status_code == 201, response.text
    stored = await db.scalar(select(User).where(User.username == username))
    assert stored is not None

    return stored


async def test_a_signup_is_given_the_tier_default_tier_name_names(
    client: AsyncClient, db_session: AsyncSession, second_test_tier: dict, test_tier: dict
):
    """Another tier was made first, so the one given is the one named, not the first there is."""
    assert test_tier["name"] == settings.DEFAULT_TIER_NAME
    assert second_test_tier["id"] < test_tier["id"]

    assert (await _signed_up(client, db_session, "newcomer")).tier_id == test_tier["id"]


async def test_a_signup_is_given_whichever_tier_default_tier_name_is_set_to(
    client: AsyncClient, db_session: AsyncSession, test_tier: dict, second_test_tier: dict, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "DEFAULT_TIER_NAME", second_test_tier["name"])

    assert (await _signed_up(client, db_session, "upgraded")).tier_id == second_test_tier["id"]


async def test_a_signup_with_no_default_tier_there_yet_is_accepted_without_one(client: AsyncClient, db_session: AsyncSession):
    assert (await _signed_up(client, db_session, "early")).tier_id is None


async def test_a_signup_is_not_given_a_default_tier_that_was_deleted(
    client: AsyncClient, db_session: AsyncSession, test_tier: dict
):
    await db_session.execute(update(Tier).where(Tier.id == test_tier["id"]).values(is_deleted=True))
    await db_session.commit()

    assert (await _signed_up(client, db_session, "late")).tier_id is None


async def test_an_account_a_provider_signs_up_is_given_the_default_tier(db_session: AsyncSession, test_tier: dict):
    context = NewUserContext(email="someone@example.com", username="someone", source="oauth", db=db_session)

    fields = await resolve_new_user_fields(auth.new_user_fields, context, auth.repo)

    assert fields["tier_id"] == test_tier["id"]
