"""Unit tests for the User model."""

import pytest
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.user.constants import PROFILE_IMAGE_URL_MAX_LENGTH
from src.modules.user.models import User


def _make_user() -> User:
    return User(
        name="Test User",
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
    )


def test_is_active_true_when_not_deleted():
    """A fresh user is active (is_deleted defaults to False)."""
    user = _make_user()
    assert user.is_deleted is False
    assert user.is_active is True


def test_is_active_false_when_soft_deleted():
    """A soft-deleted user is inactive — this is what crudauth reads to gate auth."""
    user = _make_user()
    user.is_deleted = True
    assert user.is_active is False


async def test_a_profile_url_longer_than_a_url_is_refused_by_the_column(db_session: AsyncSession, test_user: dict):
    """The schemas hold a caller to this length; the column holds the panel and a script to it."""
    asked = "https://example.com/" + "a" * PROFILE_IMAGE_URL_MAX_LENGTH

    with pytest.raises(DBAPIError, match="value too long"):
        await db_session.execute(update(User).where(User.id == test_user["id"]).values(profile_image_url=asked))

    await db_session.rollback()
