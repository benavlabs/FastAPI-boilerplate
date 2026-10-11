"""What the OAuth hook writes back, and what it leaves to the account."""

from datetime import UTC, datetime, timedelta

import pytest
from crudauth import HookContext
from crudauth.oauth import OAuthUserInfo
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.oauth_profile import refresh_the_provider_profile
from src.infrastructure.auth.setup import auth
from src.modules.user.constants import DEFAULT_PROFILE_IMAGE_URL
from src.modules.user.models import User

GOOGLE = OAuthUserInfo(
    provider="google",
    provider_user_id="google-1",
    email="ada@example.com",
    email_verified=True,
    name="Ada Lovelace",
    picture="https://provider.example/ada.png",
)


@pytest.fixture
async def account(db_session: AsyncSession, test_user: dict) -> dict:
    """The signed-in account as crudauth hands it to the hook."""
    row = (await db_session.execute(select(User).where(User.id == test_user["id"]))).scalar_one()
    return {"id": row.id, "profile_image_url": row.profile_image_url}


async def _with_the_placeholder_avatar(db_session: AsyncSession, account: dict) -> None:
    """Put the account back to the avatar it would have been created with."""
    await db_session.execute(update(User).where(User.id == account["id"]).values(profile_image_url=DEFAULT_PROFILE_IMAGE_URL))
    await db_session.commit()
    account["profile_image_url"] = DEFAULT_PROFILE_IMAGE_URL


async def _stored(db_session: AsyncSession, user_id: int) -> User:
    row = (await db_session.execute(select(User).where(User.id == user_id))).scalar_one()
    await db_session.refresh(row)
    return row


async def test_a_returning_sign_in_stamps_when_the_provider_was_last_used(db_session: AsyncSession, account: dict):
    before = datetime.now(UTC) - timedelta(seconds=1)

    await refresh_the_provider_profile(account, GOOGLE, db=db_session, created=False, context=HookContext())

    stamped = (await _stored(db_session, account["id"])).oauth_updated_at
    assert stamped is not None and stamped > before


async def test_the_sign_in_that_created_the_account_leaves_the_stamp_crudauth_wrote(db_session: AsyncSession, account: dict):
    await refresh_the_provider_profile(account, GOOGLE, db=db_session, created=True, context=HookContext())

    assert (await _stored(db_session, account["id"])).oauth_updated_at is None


async def test_the_providers_picture_fills_the_placeholder_avatar(db_session: AsyncSession, account: dict):
    await _with_the_placeholder_avatar(db_session, account)

    await refresh_the_provider_profile(account, GOOGLE, db=db_session, created=True, context=HookContext())

    assert (await _stored(db_session, account["id"])).profile_image_url == "https://provider.example/ada.png"


async def test_an_avatar_the_account_chose_is_left_alone(db_session: AsyncSession, account: dict):
    """The fixture's account carries its own picture, which a sign-in must not overwrite."""
    chosen = (await _stored(db_session, account["id"])).profile_image_url
    assert chosen != DEFAULT_PROFILE_IMAGE_URL

    await refresh_the_provider_profile(account, GOOGLE, db=db_session, created=False, context=HookContext())

    assert (await _stored(db_session, account["id"])).profile_image_url == chosen


async def test_a_provider_that_sends_no_picture_leaves_the_placeholder(db_session: AsyncSession, account: dict):
    await _with_the_placeholder_avatar(db_session, account)
    without_a_picture = GOOGLE.model_copy(update={"picture": None})

    await refresh_the_provider_profile(account, without_a_picture, db=db_session, created=False, context=HookContext())

    assert (await _stored(db_session, account["id"])).profile_image_url == DEFAULT_PROFILE_IMAGE_URL


def test_the_hook_is_registered():
    assert auth.hooks.on_oauth_login is refresh_the_provider_profile
